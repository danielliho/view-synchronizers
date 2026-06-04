#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <stdexcept>
#include <vector>

#include "NodeInfo.h"
#include "Nodes.h"

#include "salticidae/event.h"
#include "salticidae/msg.h"
#include "salticidae/network.h"
#include "salticidae/stream.h"

using salticidae::DataStream;
using salticidae::MsgNetwork;
using salticidae::NetAddr;
using salticidae::htole;
using salticidae::letoh;
using std::placeholders::_1;
using std::placeholders::_2;

using MsgNetworkByteOp = MsgNetwork<uint8_t>;

static uint64_t now_ns() {
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

struct MsgPing {
    static const uint8_t opcode = 0x0;
    DataStream serialized;
    unsigned int src;
    unsigned int dst;
    unsigned int seq;
    uint64_t sent_ns;

    MsgPing(unsigned int src, unsigned int dst, unsigned int seq, uint64_t sent_ns) {
        serialized << htole(src) << htole(dst) << htole(seq) << htole(sent_ns);
    }

    MsgPing(DataStream &&s) {
        s >> src >> dst >> seq >> sent_ns;
        src = letoh(src);
        dst = letoh(dst);
        seq = letoh(seq);
        sent_ns = letoh(sent_ns);
    }
};

struct MsgPong {
    static const uint8_t opcode = 0x1;
    DataStream serialized;
    unsigned int src;
    unsigned int dst;
    unsigned int seq;
    uint64_t sent_ns;

    MsgPong(unsigned int src, unsigned int dst, unsigned int seq, uint64_t sent_ns) {
        serialized << htole(src) << htole(dst) << htole(seq) << htole(sent_ns);
    }

    MsgPong(MsgPing &&msg) {
        src = msg.src;
        dst = msg.dst;
        seq = msg.seq;
        sent_ns = msg.sent_ns;
        serialized << htole(src) << htole(dst) << htole(seq) << htole(sent_ns);
    }

    MsgPong(DataStream &&s) {
        s >> src >> dst >> seq >> sent_ns;
        src = letoh(src);
        dst = letoh(dst);
        seq = letoh(seq);
        sent_ns = letoh(sent_ns);
    }
};

struct MsgReady {
    static const uint8_t opcode = 0x2;
    DataStream serialized;
    unsigned int src;

    MsgReady(unsigned int src) {
        serialized << htole(src);
    }

    MsgReady(DataStream &&s) {
        s >> src;
        src = letoh(src);
    }
};

const uint8_t MsgPing::opcode;
const uint8_t MsgPong::opcode;
const uint8_t MsgReady::opcode;

struct RttNet: public MsgNetworkByteOp {
    const unsigned int myid;
    const unsigned int total;
    const unsigned int samples_per_pair;
    const unsigned int runtime_seconds;
    const double round_interval_seconds;
    NodeInfo *self;
    Nodes &nodes;
    std::map<std::pair<unsigned int, unsigned int>, std::vector<double>> rtt_by_pair;  // (src, dst) -> vector of RTTs
    unsigned int sent_pings;
    unsigned int received_pongs;
    unsigned int expected_pongs;
    std::atomic<bool> stop_armed;
    salticidae::EventContext *ec_ptr;
    std::map<unsigned int, conn_t> conns;
    std::set<unsigned int> ready_peers;
    bool measurement_started;
    unsigned int next_seq;
    salticidae::TimerEvent send_ready_timer;
    salticidae::TimerEvent ready_deadline_timer;
    salticidae::TimerEvent measurement_timeout_timer;
    salticidae::TimerEvent send_round_timer;

    RttNet(const salticidae::EventContext &ec, unsigned int myid, unsigned int total, unsigned int runtime_seconds, Nodes &nodes):
        MsgNetworkByteOp(ec, []() {
            MsgNetwork::Config config;
            config.max_msg_size(1024);
            return config;
        }()),
        myid(myid),
        total(total),
        samples_per_pair(10),
        runtime_seconds(runtime_seconds),
        round_interval_seconds(0.2),
        self(nodes.find(myid)),
        nodes(nodes),
        sent_pings(0),
        received_pongs(0),
        expected_pongs(0),  // Will be set after connections
        stop_armed(false),
        ec_ptr(const_cast<salticidae::EventContext *>(&ec)),
        measurement_started(false),
        next_seq(0),
        send_ready_timer(ec, [this](salticidae::TimerEvent &) {
            this->broadcast_ready();
        }),
        ready_deadline_timer(ec, [this](salticidae::TimerEvent &) {
            if (!this->measurement_started && this->ready_peers.size() != this->conns.size()) {
                std::cerr << "rtt ready barrier deadline reached: have "
                          << this->ready_peers.size() << " / " << this->conns.size()
                          << " peer-ready messages" << std::endl;
            }
            this->start_measurement();
        }),
        measurement_timeout_timer(ec, [this](salticidae::TimerEvent &) {
            if (!this->stop_armed.load()) {
                std::cerr << "rtt timeout waiting for pong replies" << std::endl;
                this->arm_stop();
            }
        }),
        send_round_timer(ec, [this](salticidae::TimerEvent &) {
            this->send_round();
            if (this->runtime_seconds > 0 && !this->stop_armed.load()) {
                this->send_round_timer.add(this->round_interval_seconds);
            }
        }) {
        // Register one handler per message type.
        reg_handler(salticidae::generic_bind(&RttNet::on_ping_dispatch, this, _1, _2));
        reg_handler(salticidae::generic_bind(&RttNet::on_pong_dispatch, this, _1, _2));
        reg_handler(salticidae::generic_bind(&RttNet::on_ready_dispatch, this, _1, _2));
    }

    void on_ping_dispatch(MsgPing msg, const conn_t &conn) {
        on_ping(msg, conn);
    }

    void on_pong_dispatch(MsgPong msg, const conn_t &conn) {
        on_pong(msg, conn);
    }

    void on_ready_dispatch(MsgReady msg, const conn_t &conn) {
        on_ready(msg, conn);
    }

    void on_ping(MsgPing msg, const conn_t &conn) {
        // Respond to ping with pong (echo)
        send_msg(MsgPong(std::move(msg)), conn);
    }

    void on_pong(MsgPong msg, const conn_t &conn) {
        (void)conn;
        if (!measurement_started) {
            return;
        }

        auto elapsed_us = static_cast<double>(now_ns() - msg.sent_ns) / 1000.0;
        auto key = std::make_pair(msg.src, msg.dst);
        rtt_by_pair[key].push_back(elapsed_us);
        received_pongs++;
        
        std::cout << "rtt src=" << msg.src
                  << " dst=" << msg.dst
                  << " seq=" << msg.seq
                  << " us=" << std::fixed << std::setprecision(3) << elapsed_us
                  << std::endl;
        
        check_done();
    }

    void on_ready(MsgReady msg, const conn_t &conn) {
        (void)conn;
        if (measurement_started) {
            return;
        }

        auto it = conns.find(msg.src);
        if (it == conns.end()) {
            return;
        }

        ready_peers.insert(msg.src);
        if (ready_peers.size() == conns.size()) {
            start_measurement();
        }
    }

    void check_done() {
        if (runtime_seconds > 0) {
            return;
        }
        if (measurement_started && expected_pongs > 0 &&
            sent_pings == expected_pongs && received_pongs == expected_pongs) {
            arm_stop();
        }
    }

    void arm_stop() {
        bool expected = false;
        if (!stop_armed.compare_exchange_strong(expected, true)) return;
        send_ready_timer.del();
        ready_deadline_timer.del();
        measurement_timeout_timer.del();
        send_round_timer.del();
        if (ec_ptr != nullptr) {
            ec_ptr->stop();
        }
    }

    void send_round() {
        if (!measurement_started || stop_armed.load()) {
            return;
        }

        for (const auto &entry : conns) {
            auto peer_id = entry.first;
            auto &conn = entry.second;
            send_msg(MsgPing(myid, peer_id, next_seq, now_ns()), conn);
            sent_pings++;
            expected_pongs++;
        }
        next_seq++;
    }

    void broadcast_ready() {
        for (const auto &entry : conns) {
            send_msg(MsgReady(myid), entry.second);
        }

        if (conns.empty()) {
            start_measurement();
            return;
        }

        if (ready_peers.size() == conns.size()) {
            start_measurement();
        }
    }

    void start_measurement() {
        if (measurement_started) {
            return;
        }

        measurement_started = true;
        send_ready_timer.del();
        ready_deadline_timer.del();

        expected_pongs = 0;
        if (expected_pongs == 0) {
            if (conns.empty()) {
                arm_stop();
                return;
            }
        }

        std::cout << "rtt start node=" << myid
                  << " peers=" << conns.size()
                  << " mode=" << (runtime_seconds > 0 ? "timeout" : "samples")
                  << std::endl;

        if (runtime_seconds > 0) {
            // Timeout mode: keep generating RTT rounds until runtime expires.
            send_round();
            send_round_timer.add(round_interval_seconds);
        } else {
            // Sample mode: fixed number of rounds per peer.
            for (unsigned int sample = 0; sample < samples_per_pair; sample++) {
                send_round();
            }
        }

        double timeout_sec = runtime_seconds > 0 ? static_cast<double>(runtime_seconds) : 10.0;
        measurement_timeout_timer.add(timeout_sec);
        check_done();
    }

    bool connect_and_measure() {
        if (self == NULL) {
            throw std::runtime_error("could not find own node entry in config");
        }

        std::string addr_str = self->getHost() + ":" + std::to_string(self->getRPort());
        auto listen_addr = NetAddr(addr_str);
        start();
        listen(listen_addr);

        // Phase 1: All nodes listen (5 seconds for cluster startup spread with 12 nodes)
        std::this_thread::sleep_for(std::chrono::seconds(5));

        // Phase 2: Connect to all other nodes (with retries)
        for (unsigned int j = 0; j < total; j++) {
            if (j == myid) continue;
            
            NodeInfo *other = nodes.find(j);
            if (other == NULL) {
                continue;
            }

            std::string peer_addr_str = other->getHost() + ":" + std::to_string(other->getRPort());
            auto peer_addr = NetAddr(peer_addr_str);
            
            // Try connecting up to 3 times with 0.5 second delays
            for (int attempt = 0; attempt < 3; attempt++) {
                try {
                    auto conn = connect_sync(peer_addr);
                    conns[j] = conn;
                    break;
                } catch (const std::exception &e) {
                    if (attempt < 2) {
                        std::this_thread::sleep_for(std::chrono::milliseconds(500));
                    }
                }
            }
        }

        // Phase 3: Enter dispatch and only start RTT once peers signal ready.
        send_ready_timer.add(0.2);
        ready_deadline_timer.add(10.0);

        return true;
    }

    void on_peer_connect(const conn_t &conn) {
        // Optional: track connected peers
    }

    void on_peer_disconnect(const conn_t &conn) {
        // Optional: track disconnected peers
    }

    void write_summary() const {
        const char *stats_dir = std::getenv("STATS_DIR");
        if (stats_dir == NULL || *stats_dir == '\0') return;

        std::string path = std::string(stats_dir) + "/rtt-node-" + std::to_string(myid) + ".txt";
        std::ofstream out(path);
        if (!out.is_open()) return;

        out << "# Node " << myid << " RTT measurements (all pairs)" << std::endl;
        out << "# src dst samples avg_us min_us max_us" << std::endl;

        for (unsigned int j = 0; j < total; j++) {
            if (j == myid) continue;
            
            auto key = std::make_pair(myid, j);
            auto it = rtt_by_pair.find(key);
            if (it == rtt_by_pair.end() || it->second.empty()) {
                out << myid << " " << j << " 0 0 0 0" << std::endl;
                continue;
            }

            const auto &samples = it->second;
            double sum = 0.0;
            double min_val = samples[0];
            double max_val = samples[0];
            for (double v : samples) {
                sum += v;
                if (v < min_val) min_val = v;
                if (v > max_val) max_val = v;
            }
            double avg = sum / samples.size();

            out << myid << " " << j 
                << " " << samples.size()
                << " " << std::fixed << std::setprecision(3) << avg
                << " " << std::fixed << std::setprecision(3) << min_val
                << " " << std::fixed << std::setprecision(3) << max_val
                << std::endl;
        }
    }
};

int main(int argc, char **argv) {
    if (argc < 4) {
        std::cerr << "usage: " << argv[0] << " <id> <num_nodes> <config_file> [timeout_seconds]" << std::endl;
        return 1;
    }

    unsigned int myid = static_cast<unsigned int>(std::stoul(argv[1]));
    unsigned int num_nodes = static_cast<unsigned int>(std::stoul(argv[2]));
    std::string config_file = argv[3];
    unsigned int runtime_seconds = 0;
    if (argc >= 5) {
        runtime_seconds = static_cast<unsigned int>(std::stoul(argv[4]));
    }

    Nodes nodes(config_file, num_nodes);
    salticidae::EventContext ec;
    RttNet net(ec, myid, num_nodes, runtime_seconds, nodes);
    bool needs_dispatch = net.connect_and_measure();
    if (needs_dispatch) {
        ec.dispatch();
    }
    net.write_summary();
    return 0;
}