#include <iostream>
#include <fstream>
#include <unistd.h>
#include <unistd.h>
#include <stdio.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <stdlib.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <string>
#include <cstring>
#include <thread>
#include <openssl/pem.h>
#include <openssl/rsa.h>
#include <openssl/rand.h>

#include "Message.h"
#include "RData.h"
#include "Signs.h"
#include "Nodes.h"
#include "KeysFun.h"
#include "Handler.h"

#include "salticidae/conn.h"



int main(int argc, char const *argv[]) {
  fd_set read_fds;
  fd_set write_fds;
  KeysFun kf;

  // Geting inputs
  if (DEBUG) std::cout << KYEL << "parsing inputs" << KNRM << std::endl;

  unsigned int myid = 0;
  if (argc > 1) { sscanf(argv[1], "%d", &myid); }
  std::cout << KYEL << "[id=" << myid << "]" << KNRM << std::endl;

  unsigned int numFaults = 1;
  if (argc > 2) { sscanf(argv[2], "%d", &numFaults); }
  std::cout << KYEL << "[" << myid << "]#faults=" << numFaults << KNRM << std::endl;

  unsigned int constFactor = 3; // default value: by default, there are 3f+1 nodes
  if (argc > 3) { sscanf(argv[3], "%d", &constFactor); }
  std::cout << KYEL << "[" << myid << "]constFactor=" << constFactor << KNRM << std::endl;

  unsigned int numViews = 10;
  if (argc > 4) { sscanf(argv[4], "%d", &numViews); }
  std::cout << KYEL << "[" << myid << "]#views=" << numViews << KNRM << std::endl;

  double timeout = 5; // timeout in seconds
  if (argc > 5) { sscanf(argv[5], "%lf", &timeout); }
  std::cout << KYEL << "[" << myid << "]timeout=" << timeout << KNRM << std::endl;

  unsigned int timeoutMul = 1; // timeoutMul
  if (argc > 6) { sscanf(argv[6], "%d", &timeoutMul); }
  std::cout << KYEL << "[" << myid << "]timeoutMul=" << timeoutMul << KNRM << std::endl;

  unsigned int timeoutDiv = 1; // timeoutDiv
  if (argc > 7) { sscanf(argv[7], "%d", &timeoutDiv); }
  std::cout << KYEL << "[" << myid << "]timeoutDiv=" << timeoutDiv << KNRM << std::endl;

  unsigned int opdist = 0; // OP cases
  if (argc > 8) { sscanf(argv[8], "%d", &opdist); }
  std::cout << KYEL << "[" << myid << "]opdist=" << opdist << KNRM << std::endl;

  unsigned int syncPeriod = 0;
  if (argc > 9) { sscanf(argv[9], "%d", &syncPeriod); }
  std::cout << KYEL << "[" << myid << "]syncPeriod=" << syncPeriod << KNRM << std::endl;

  unsigned int joinPeriod = 0;
  if (argc > 10) { sscanf(argv[10], "%d", &joinPeriod); }
  std::cout << KYEL << "[" << myid << "]joinPeriod=" << joinPeriod << KNRM << std::endl;

  unsigned int numJoiners = 0;
  if (argc > 11) { sscanf(argv[11], "%d", &numJoiners); }
  std::cout << KYEL << "[" << myid << "]numJoiners=" << numJoiners << KNRM << std::endl;

  unsigned int quant1 = 0;
  if (argc > 12) { sscanf(argv[12], "%d", &quant1); }
  std::cout << KYEL << "[" << myid << "]quant1=" << quant1 << KNRM << std::endl;

  unsigned int quant2 = 0;
  if (argc > 13) { sscanf(argv[13], "%d", &quant2); }
  std::cout << KYEL << "[" << myid << "]quant2=" << quant2 << KNRM << std::endl;

  unsigned int skip = 0;
  if (argc > 14) { sscanf(argv[14], "%d", &skip); }
  std::cout << KYEL << "[" << myid << "]skip=" << skip << KNRM << std::endl;


  // -- Public key
  KEY priv;
  // Set private key - nothing special to do for EC
#if defined(KK_RSA4096) || defined(KK_RSA2048)
  priv = RSA_new();
#endif

// NOTE: For now, when using the accumulator, all nodes use the same keys, as public keys need to be shared
// between 'trusted' components and 'normal' components, and currently keys are hard coded in trusted components.
// We only do that for ec256, because that's the only one we use really right now.
// We do the same for public keys below.
#if /*(defined(ACCUM) || defined(COMB)) &&*/ defined(KK_EC256)
  BIO *bio = BIO_new(BIO_s_mem());
  int w = BIO_write(bio,priv_key256,sizeof(priv_key256));
  priv = PEM_read_bio_ECPrivateKey(bio, NULL, NULL, NULL);
#else
  if (kf.loadPrivateKey(myid,&priv)) {
    std::cout << KYEL << "loading private key failed" << KNRM << std::endl;
    return 0;
  }
#endif

#ifdef KK_EC256
  if (DEBUG1) { std::cout << KYEL << "checking private key" << KNRM << std::endl; }
  if (!EC_KEY_check_key(priv)) {
    std::cout << KYEL << "invalid key" << KNRM << std::endl;
  }
  if (DEBUG1) { std::cout << KYEL << "checked private key (sign size=" << ECDSA_size(priv) << ")" << KNRM << std::endl; }
#endif


  unsigned int numNodes = (constFactor*numFaults)+1;
  std::string confFile = "config";
  Nodes nodes(confFile,numNodes);


  // -- Public keys
  for (unsigned int i = 0; i < numNodes; i++) {
    //public key
    KEY pub;
    // Set public key - nothing special to do for EC
#if defined(KK_RSA4096) || defined(KK_RSA2048)
    pub = RSA_new();
#endif
#if /*(defined(ACCUM) || defined(COMB)) &&*/ defined(KK_EC256)
    BIO *bio = BIO_new(BIO_s_mem());
    int w = BIO_write(bio,pub_key256,sizeof(pub_key256));
    pub = PEM_read_bio_EC_PUBKEY(bio, NULL, NULL, NULL);
#else
    kf.loadPublicKey(i,&pub);
#endif
    if (DEBUG) std::cout << KMAG << "id: " << i << KNRM << std::endl;
    nodes.setPub(i,pub);
  }


  // Initializing handler
  if (DEBUG) std::cout << KYEL << "initializing handler" << KNRM << std::endl;

  long unsigned int size = std::max({sizeof(MsgTransaction), sizeof(MsgReply), sizeof(MsgStart)});
  size = std::max({size,
                   sizeof(MsgNewViewRB),
                   sizeof(MsgLdrPrepareRB),
                   sizeof(MsgBckPrepareRB),
                   sizeof(MsgLdrPreCommitRB),
                   sizeof(MsgBckPreCommitRB),
                   sizeof(MsgDecideRB),
                   sizeof(MsgSync),
                   sizeof(MsgSyncTC),
                   sizeof(MsgSyncVote),
                   sizeof(MsgSyncVoteQc),
                   sizeof(MsgJoin)});

  if (DEBUG0) {
    std::cout << KYEL << "[" << myid << "]sizes"
              << ":transaction="    << sizeof(MsgTransaction)
              << ";newviewrb="      << sizeof(MsgNewViewRB)
              << ";ldrpreparerb="   << sizeof(MsgLdrPrepareRB)
              << ";bckpreparerb="   << sizeof(MsgBckPrepareRB)
              << ";ldrprecommitrb=" << sizeof(MsgLdrPreCommitRB)
              << ";bckprecommitrb=" << sizeof(MsgBckPreCommitRB)
              << ";deciderb="       << sizeof(MsgDecideRB)
              << ";sync="           << sizeof(MsgSync)
              << ";synctc="         << sizeof(MsgSyncTC)
              << ";syncvote="       << sizeof(MsgSyncVote)
              << ";syncvoteqc="     << sizeof(MsgSyncVoteQc)
              << ";join="           << sizeof(MsgJoin)
              << KNRM << std::endl;
  }
  if (DEBUG0) std::cout << KYEL << "[" << myid << "]max-msg-size=" << size << KNRM << std::endl;
  salticidae::ConnPool::Config config;
  //config.nworker(2);
  //config.recv_chunk_size(200000);
  //config.max_recv_buff_size(6144);
  //config.max_send_buff_size(6144);
  PeerNet::Config pconfig(config);
  // TODO: for some reason 'size' is not quite right
  //size = 2 * size;
  //size = size + (size / 10);
  pconfig.max_msg_size(size);
  ClientNet::Config cconfig;
  cconfig.max_msg_size(size);
  //config.ping_period(2);
  if (DEBUG1) std::cout << KYEL << "[" << myid << "]starting handler" << KNRM << std::endl;
  Handler handler(kf,myid,timeout,timeoutMul,timeoutDiv,opdist,constFactor,numFaults,numViews,syncPeriod,joinPeriod,numJoiners,quant1,quant2,skip,nodes,priv,pconfig,cconfig);

  return 0;
};
