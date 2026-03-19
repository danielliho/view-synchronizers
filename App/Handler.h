#ifndef HANDLER_H
#define HANDLER_H


#include <map>
#include <set>
#include <random>

#include "Message.h"
#include "Nodes.h"
#include "Log.h"
#include "Stats.h"
#include "VJust.h"
#include "FVJust.h"
#include "RBBlock.h"

#include "../Enclave/user_types.h"



// ------------------------------------
// SGX related stuff
#include "Enclave_u.h"
#include "sgx_urts.h"
#include "sgx_utils/sgx_utils.h"
// ------------------------------------


//#define NDEBUG


// Salticidae related stuff
#include <memory>
#include <cstdio>
#include <functional>
#include "salticidae/msg.h"
#include "salticidae/event.h"
#include "salticidae/network.h"
#include "salticidae/stream.h"

using std::placeholders::_1;
using std::placeholders::_2;


using PeerNet     = salticidae::PeerNetwork<uint8_t>;
using Peer        = std::tuple<PID,salticidae::PeerId>;
using Peers       = std::vector<Peer>;
using ClientNet   = salticidae::ClientNetwork<uint8_t>;
using MsgNet      = salticidae::MsgNetwork<uint8_t>;
// the bool is true if the client hasn't stopped yet
// the 1st int is the number of transactions received from the client
// the 2nd int is the number of transactions replied to
using ClientNfo   = std::tuple<bool,unsigned int,unsigned int,ClientNet::conn_t>;
using Clients     = std::map<CID,ClientNfo>;
using rep_queue_t = salticidae::MPSCQueueEventDriven<std::pair<TID,CID>>;
using Time        = std::chrono::time_point<std::chrono::steady_clock>;


class Handler {

 private:
  PID myid;
  double initTimeout;            // timeout after which nodes start a new view (initial value)
  double timeout;                // timeout after which nodes start a new view
  unsigned int timeoutMul = 1;   // factor used to multiply timeout with when timeouts occur
  unsigned int timeoutDiv = 1;   // factor used to devide timeout with when progress is made
  unsigned int opdist;           // OP cases
  unsigned int numFaults;        // number of faults
  unsigned int qsize;            // quorum size
  unsigned int total;            // total number of nodes
  Nodes nodes;                   // collection of the other nodes
  KEY priv;                      // private key
  View view = 0;                 // current view - initially 0
  unsigned int maxViews = 0;     // 0 means no constraints
  KeysFun kf;                    // To access crypto functions

  salticidae::EventContext pec; // peer ec
  salticidae::EventContext cec; // request ec
  //salticidae::EventContext rep_ec;
  PeerNet pnet;
  Peers peers;
  Clients clients;
  ClientNet cnet;
  std::thread c_thread; // request thread
  //std::thread rep_thread; // reply thread
  rep_queue_t rep_queue;
  salticidae::BoxObj<salticidae::ThreadCall> req_tcall;
  //salticidae::BoxObj<salticidae::ThreadCall> rep_tcall;
  unsigned int viewsWithoutNewTrans = 0;
  bool started = false;
  bool stopped = false;
  salticidae::TimerEvent timer;
  View timerView; // view at which the timer was started

  std::list<Transaction> transactions; // current waiting to be processed
  std::map<View,Block> blocks; // blocks received in each view
  std::map<View,bool> prepared; // whether a view was prepared -> true for fast mode, false for slow mode
  std::map<View,JBlock> jblocks; // blocks received in each view (Chained baseline)
  Log log; // log of messages

  // Used for the accumulator version
  Cert qcprep;

  // Used in the 'OP' version - the latest prepare certificate
  OPprepare opprep;
  // and the latest proposal
  OPprp opprop;

  // -----------------------------
  // -- Rollback variables
  // --
  Session session = 0;
  // Last prepare certificate sent
  RBprepareAuth lastRBvote;
  // Last prepare quorum certificate
  RBprepareAuths lastRBprep;
  // Last store 1-certificate
  RBstoreAuth lastRBstore;
  // Last executed view
  View lastRBexec = 0;
  // To keep track of the join requests that have been agreed upon
  Joins agreedJoins;
  // Joins that have been received but not yet agreed upon
  Joins receivedJoins;
  // blocks received in each view
  std::map<SView,RBBlock> rbblocks;
  // maps hashes to the corresponding blocks
  std::map<Hash,RBBlock> rbhblocks;
  // Latest sessions nodes have joined
  Session sessions[MAX_NUM_NODES];
  // synchronization period
  unsigned int syncPeriod = 0;
  // joining period
  unsigned int joinPeriod = 0;
  // number of nodes to rejoin per session
  unsigned int numJoiners = 0;
  // true if the node is rejoining and therefore not handling messages
  bool rejoining = false;
  // last join message sent
  Join lastJoin;
  // true if the node is synchronizing -- called wishToAdvance
  bool synchronizing = false;
  // number of times a sync for a session has been attempted
  unsigned int syncAttempts = 0;
  // view at which nodes have last synced
  unsigned int lastSync = 0;
  // --
  // -------

  // -------------------
  // Pacemaker variables
  FVJust lastPMstore;
  // --------

  unsigned int quant1 = 0;
  unsigned int quant2 = 0;
  unsigned int skip   = 0;

  //void newview_handler(MsgNewView &&msg, const PeerNet::conn_t &conn);

  // Initializes SGX-related stuff
  int initializeSGX();
//  void ocall_recCtime();

  void printClientInfo();

  void printNowTime(std::string col, std::string msg);

  // returns the leader of view 'v'
  unsigned int getLeaderOf(View v);

  // returns the current leader
  unsigned int getCurrentLeader();

  // true iff 'myid' is the leader of view 'v'
  bool amLeaderOf(View v);

  // ture iff 'myid' is the leader of the current view
  bool amCurrentLeader();
  std::string amCurrentLeaderStr();

  // used to print debugging info
  std::string nfo();

  bool timeToStop();
  void recordStats();
  void setTimer();

  Sign Ssign(KEY priv, PID signer, std::string text);
  bool Sverify(Signs signs, PID id, Nodes nodes, std::string s);

  // To stop clients once all have stopped
  //void checkStopClients();

  Block createNewBlock(Hash hash);

  void replyTransactions(Transaction *transactions);
  void replyHash(Hash hash);

  // send messages
  //void sendData(unsigned int size, char *data, Peers recipients);
  void sendMsgNewView(MsgNewView msg, Peers recipients);
  void sendMsgPrepare(MsgPrepare msg, Peers recipients);
  void sendMsgLdrPrepare(MsgLdrPrepare msg, Peers recipients);
  void sendMsgPreCommit(MsgPreCommit msg, Peers recipients);
  void sendMsgCommit(MsgCommit msg, Peers recipients);

  // for leaders to start the phase where nodes will log prepare certificates
  void initiatePrepare(RData rdata);
  // for leaders to start the phase where nodes will log lock certificates
  void initiatePrecommit(RData rdata);
  // for leaders to start the phase where nodes execute
  void initiateCommit(RData rdata);

  //bool verifyPrepare(Message<Proposal> msg);
  bool verifyTransaction(MsgTransaction msg);
  //bool verifyStart(MsgStart msg);

  bool verifyJust(Just just);

  // To start the code
  void getStarted();

  void prepare();

  void respondToProposal(Just justNv, Block b);
  void respondToPrepareJust(Just justPrep);
  void respondToPreCommitJust(Just justPc);

  Peers from_to_peers(PID id1, PID id2);
  Peers remove_from_peers(PID id);
  Peers keep_from_peers(PID id);

  void startNewViewOnTimeout();


  // ------------------------------------------------------------
  // Baseline and Cheap
  // ------

  void executeRData(RData rdata);
  void handleEarlierMessages();
  void startNewView();

  // Wrappers around the TEE functions
  Just callTEEsign();
  Just callTEEstore(Just j);
  Just callTEEprepare(Hash h, Just j);

  void handleNewview(MsgNewView msg);
  void handlePrepare(MsgPrepare msg);
  void handleLdrPrepare(MsgLdrPrepare msg);
  void handlePrecommit(MsgPreCommit msg);
  void handleCommit(MsgCommit msg);

  void handleTransaction(MsgTransaction msg);
  //void handleStart(MsgStart msg);

  void handle_transaction(MsgTransaction msg, const ClientNet::conn_t &conn);
  void handle_start(MsgStart msg, const ClientNet::conn_t &conn);
  //void handle_stop(MsgStop msg, const ClientNet::conn_t &conn);

  Just justNV;

  // ------------------------------------------------------------
  // Pacemaker
  // ------

  Sync callTEEsync(RBstoreAuth store);
  Join callTEEjoinRequest(View v);
  SyncVoteAuth callTEEsyncVote(RBaccumSyncAuth acc, INonces nonces);
  RBstoreAuth callTEEsyncEnd(SyncVoteAuths votes);

  void sendMsgJoin(MsgJoin wish, Peers recipients);
  void sendMsgSync(MsgSync sync, Peers recipients);
  void sendMsgSyncTC(MsgSyncTC msg, Peers recipients);
  void sendMsgSyncVote(MsgSyncVote msg, Peers recipients);
  void sendMsgSyncVoteQc(MsgSyncVoteQc msg, Peers recipients);

  void wishToAdvanceOnSync(Sync msg, PID leader);
  void wishToAdvance();
  void wishToJoin();

  Joins getPreparedJoins(Session s, View v);

  void handleJoin(MsgJoin msg);
  void handleSync(Sync msg);
  void handleSyncTC(MsgSyncTC msg);
  void handleSyncVote(MsgSyncVote msg);
  void handleSyncVoteQc(MsgSyncVoteQc msg);

  void handle_join(MsgJoin msg, const PeerNet::conn_t &conn);
  void handle_sync(MsgSync msg, const PeerNet::conn_t &conn);
  void handle_sync_tc(MsgSyncTC msg, const PeerNet::conn_t &conn);
  void handle_sync_vote(MsgSyncVote msg, const PeerNet::conn_t &conn);
  void handle_sync_vote_qc(MsgSyncVoteQc msg, const PeerNet::conn_t &conn);

  RBprepareAuth callTEEprepareRB(Hash hblock);
  RBstoreAuth callTEEstoreRB(RBprepareAuths j);
  RBnewviewAuth callTEEnewviewRB(RBstoreAuth store);
  RBaccumNvAuth callTEEaccumNvRB(RBnewviewAuth newview, std::set<RBnewviewAuth> newviews);
  RBaccumSyncAuth callTEEaccumSyncRB(Sync sync, std::set<Sync> syncs);

  unsigned int nextSync();

  void acceptJoins();
  RBnewviewAuth highestNewViewRB(std::set<RBnewviewAuth> *newviews);
  Sync highestSync(std::set<Sync> *syncs);
  RBBlock createNewRBBlock(Hash hash);
  void prepareRB();
  void preCommitRB(View view);
  void respondToLdrPrepareRB(Hash Hblock, RBaccumNvAuth acc);
  void respondToLdrPreCommitRB(RBprepareAuths prep);
  void decideRB(RBstore store);
  void executeRB(RBstoreAuths store);
  void startNewViewRB(RBstoreAuth store);
  void startNewViewOrSyncRB(RBstoreAuth store);
  void startNewViewOrJoinRB(RBstoreAuth store);
  void handleEarlierMessagesRB();
  void handleEarlierMessagesSync();

  void sendMsgLdrPrepareRB(MsgLdrPrepareRB msg, Peers recipients);
  void sendMsgBckPrepareRB(MsgBckPrepareRB msg, Peers recipients);
  void sendMsgLdrPreCommitRB(MsgLdrPreCommitRB msg, Peers recipients);
  void sendMsgBckPreCommitRB(MsgBckPreCommitRB msg, Peers recipients);
  void sendMsgDecideRB(MsgDecideRB msg, Peers recipients);
  void sendMsgNewViewRB(MsgNewViewRB msg, Peers recipients);

  void handleNewviewRB(MsgNewViewRB msg);
  void handleLdrPrepareRB(RBBlock block, RBprepareAuth prep, RBaccumNvAuth acc);
  void handleBckPrepareRB(MsgBckPrepareRB msg);
  void handleLdrPreCommitRB(RBprepareAuths cert);
  void handleBckPreCommitRB(MsgBckPreCommitRB msg);
  void handleDecideRB(MsgDecideRB msg);

  void handle_newviewRB(MsgNewViewRB msg, const PeerNet::conn_t &conn);
  void handle_ldrprepareRB(MsgLdrPrepareRB msg, const PeerNet::conn_t &conn);
  void handle_bckprepareRB(MsgBckPrepareRB msg, const PeerNet::conn_t &conn);
  void handle_ldrprecommitRB(MsgLdrPreCommitRB msg, const PeerNet::conn_t &conn);
  void handle_bckprecommitRB(MsgBckPreCommitRB msg, const PeerNet::conn_t &conn);
  void handle_decideRB(MsgDecideRB msg, const PeerNet::conn_t &conn);

 public:
  Handler(KeysFun kf,
          PID id,
          double timeout,
          unsigned int timeoutMul,
          unsigned int timeoutDiv,
          unsigned int opdist,
          unsigned int constFactor,
          unsigned int numFaults,
          unsigned int maxViews,
          unsigned int syncPeriod,
          unsigned int joinPeriod,
          unsigned int numJoiners,
          unsigned int quant1,
          unsigned int quant2,
          unsigned int skip,
          Nodes nodes,
          KEY priv,
          PeerNet::Config pconf,
          ClientNet::Config cconf);
};


#endif
