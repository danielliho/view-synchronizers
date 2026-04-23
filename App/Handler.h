#ifndef HANDLER_H
#define HANDLER_H


#include <map>
#include <set>
#include <random>

#include "Message.h"
#include "Nodes.h"
#include "Log.h"
#include "Stats.h"
#include "Vote.h"
#include "FJust.h"
#include "PJust.h"
#include "HJust.h"
#include "VJust.h"
#include "FVJust.h"
#include "RBBlock.h"

#include "../Enclave/user_types.h"



// ------------------------------------
// SGX related stuff
#if defined(BASIC_CHEAP) || defined(BASIC_QUICK) || defined(BASIC_CHEAP_AND_QUICK) || defined(BASIC_DAMYSUS_PACEMAKER) || defined(BASIC_DAMYSUS3_PACEMAKER) || defined(BASIC_DAMYSUS_ACHILLES) || defined(BASIC_DAMYSUS_ROTE) || defined(BASIC_FREE) || defined(BASIC_ROLL) || defined(BASIC_ONEP) || defined(BASIC_ONEPB) || defined(BASIC_ONEPC) || defined(CHAINED_CHEAP_AND_QUICK)
//
#include "Enclave_u.h"
#include "sgx_urts.h"
#include "sgx_utils/sgx_utils.h"
//
#else // i.e.,  defined(BASIC_BASELINE) || defined(CHAINED_BASELINE) || defined(BASIC_QUICK_DEBUG) || defined(CHAINED_CHEAP_AND_QUICK_DEBUG)
//
#include "TrustedFun.h"
#include "TrustedAccum.h"
#include "TrustedComb.h"
#include "TrustedCh.h"
#include "TrustedChComb.h"
//
#endif
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
  Epoch epoch = 0;
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
  View lastTimeoutWishedView = 0;
  Epoch lastTimeoutWishedEpoch = 0;

  std::list<Transaction> transactions; // current waiting to be processed
  std::map<View,Block> blocks; // blocks received in each view
  std::map<View,bool> prepared; // whether a view was prepared -> true for fast mode, false for slow mode
  std::map<View,JBlock> jblocks; // blocks received in each view (Chained baseline)
  std::map<View,CBlock> cblocks; // blocks received in each view (Chained Cheap&Quick)
  Log log; // log of messages

  // Used for the accumulator version
  Cert qcprep;

  // Used in the 'free' version - the new-view certificate generated last
  FJust nvjust;
  // Used in the 'free' version - the prepare certificate received last
  PJust prepjust;

  // Used in the 'ROTE' version - catching up with view in startNewViewFree
  bool startingNewView = false;

  std::map<PID,View> latestRoteCounters; // latest counters/views receveid in MsgCounterRote messages

  // Tracks which replicas requested a jump to a given view.
  std::map<View,std::set<PID>> wishesToAdvanceView;
  std::map<Epoch,std::set<PID>> wishesToAdvanceEpoch;
  bool wishing = false;

  std::set<Hash> acceptedNoncesAchilles; // set of nonces that led to a successful restart

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

  // returns the total number of nodes
  unsigned int getTotal();

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

  //void sendMsgReply(MsgReply msg, ClientNet::conn_t recipient);

  void sendMsgNewViewAcc(MsgNewViewAcc msg, Peers recipients);
  void sendMsgLdrPrepareAcc(MsgLdrPrepareAcc msg, Peers recipients);
  void sendMsgPrepareAcc(MsgPrepareAcc msg, Peers recipients);
  void sendMsgPreCommitAcc(MsgPreCommitAcc msg, Peers recipients);

  void sendMsgNewViewComb(MsgNewViewComb msg, Peers recipients);
  void sendMsgLdrPrepareComb(MsgLdrPrepareComb msg, Peers recipients);
  void sendMsgPrepareComb(MsgPrepareComb msg, Peers recipients);
  void sendMsgPreCommitComb(MsgPreCommitComb msg, Peers recipients);

  void sendMsgNewViewFree(MsgNewViewFree msg, Peers recipients);
  void sendMsgLdrPrepareFree(MsgLdrPrepareFree msg, Peers recipients);
  void sendMsgBckPrepareFree(MsgBckPrepareFree msg, Peers recipients);
  void sendMsgPrepareFree(MsgPrepareFree msg, Peers recipients);
  void sendMsgPreCommitFree(MsgPreCommitFree msg, Peers recipients);

  void sendMsgLdrPrepareOPA(MsgLdrPrepareOPA msg, Peers recipients);
  void sendMsgLdrPrepareOPB(MsgLdrPrepareOPB msg, Peers recipients);
  void sendMsgLdrPrepareOPC(MsgLdrPrepareOPC msg, Peers recipients);
  void sendMsgPreCommitOP(MsgPreCommitOP msg, Peers recipients);
  void sendMsgNewViewOP(MsgNewViewOPA msg, Peers recipients);
  void sendMsgNewViewOP(MsgNewViewOPB msg, Peers recipients);
  void sendMsgNewViewOP(MsgNewViewOPBB msg, Peers recipients);
  void sendMsgBckPrepareOP(MsgBckPrepareOP msg, Peers recipients);
  void sendMsgLdrAddOP(MsgLdrAddOP msg, Peers recipients);
  void sendMsgBckAddOP(MsgBckAddOP msg, Peers recipients);

  void sendMsgNewViewCh(MsgNewViewCh msg, Peers recipients);
  void sendMsgPrepareCh(MsgPrepareCh msg, Peers recipients);
  void sendMsgLdrPrepareCh(MsgLdrPrepareCh msg, Peers recipients);

  void sendMsgNewViewChComb(MsgNewViewChComb msg, Peers recipients);
  void sendMsgPrepareChComb(MsgPrepareChComb msg, Peers recipients);
  void sendMsgLdrPrepareChComb(MsgLdrPrepareChComb msg, Peers recipients);

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

  bool verifyLdrPrepareComb(MsgLdrPrepareComb msg);
  bool verifyPreCommitCombCert(MsgPreCommitComb msg);

  bool verifyLdrPrepareFree(HAccum acc, Block block);
  bool verifyPreCommitFreeCert(MsgPreCommitFree msg);

  Accum newviews2acc(std::set<MsgNewViewAcc> newviews);

  // To start the code
  void getStarted();

  void prepare();

  void respondToProposal(Just justNv, Block b);
  void respondToPrepareJust(Just justPrep);
  void respondToPreCommitJust(Just justPc);

  Peers from_to_peers(PID id1, PID id2);
  Peers remove_from_peers(PID id);
  Peers keep_from_peers(PID id);
  Peers getNextQsizeLeaders(View v);
  bool amNextQsizeLeader(View v);

  //View synchronization stuff
  void wishToAdvanceView(View v);
  
  void handleWishToAdvanceView(MsgWishToAdvanceView msg, PID sender);
  void handle_wishtoadvanceview(MsgWishToAdvanceView msg, const PeerNet::conn_t &conn);
  void sendMsgWishToAdvanceView(MsgWishToAdvanceView msg, Peers recipients);

  void handleViewCertificate(MsgViewCertificate msg, PID sender);
  void handle_viewcertificate(MsgViewCertificate msg, const PeerNet::conn_t &conn);
  void sendMsgViewCertificate(MsgViewCertificate msg, Peers recipients);

  void wishToAdvanceEpoch(Epoch e);
  void handleWishToAdvanceEpoch(MsgWishToAdvanceEpoch msg, PID sender);
  void handle_wishtoadvanceepoch(MsgWishToAdvanceEpoch msg, const PeerNet::conn_t &conn);
  void sendMsgWishToAdvanceEpoch(MsgWishToAdvanceEpoch msg, Peers recipients);

  void handleEpochCertificate(MsgEpochCertificate msg, PID sender);
  void handle_epochcertificate(MsgEpochCertificate msg, const PeerNet::conn_t &conn);
  void sendMsgEpochCertificate(MsgEpochCertificate msg, Peers recipients);


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
  bool callTEEverify(Just j);

  void handleNewview(MsgNewView msg);
  void handlePrepare(MsgPrepare msg);
  void handleLdrPrepare(MsgLdrPrepare msg);
  void handlePrecommit(MsgPreCommit msg);
  void handleCommit(MsgCommit msg);
  void handleTransaction(MsgTransaction msg);
  //void handleStart(MsgStart msg);

  void handle_newview(MsgNewView msg, const PeerNet::conn_t &conn);
  void handle_prepare(MsgPrepare msg, const PeerNet::conn_t &conn);
  void handle_ldrprepare(MsgLdrPrepare msg, const PeerNet::conn_t &conn);
  void handle_precommit(MsgPreCommit msg, const PeerNet::conn_t &conn);
  void handle_commit(MsgCommit msg, const PeerNet::conn_t &conn);
  void handle_transaction(MsgTransaction msg, const ClientNet::conn_t &conn);
  void handle_start(MsgStart msg, const ClientNet::conn_t &conn);
  //void handle_stop(MsgStop msg, const ClientNet::conn_t &conn);



  // ------------------------------------------------------------
  // Quick
  // ------

  void executeCData(CData<Hash,Void> cdata);
  void handleEarlierMessagesAcc();
  void startNewViewAcc();
  void startNewViewAccOn();
  void startNewViewOrSyncAcc();

  // For leaders to start preparing
  void prepareAcc();
  // For leaders to start pre-committing
  void preCommitAcc(CData<Hash,Void> data);
  // For leaders to start deciding
  void decideAcc(CData<Hash,Void> data);

  // For backups to respond to correct MsgLdrPrepareAcc messages received from leaders
  void respondToLdrPrepareAcc(Block block);
  // For backups to respond to MsgPrepareAcc messages receveid from leaders
  void respondToPrepareAcc(MsgPrepareAcc msg);
  // For backups to respond to MsgPreCommitAcc messages receveid from leaders
  void respondToPreCommitAcc(MsgPreCommitAcc msg);

  Accum callTEEaccum(Vote<Void,Cert> votes[MAX_NUM_SIGNATURES]);
  Accum callTEEaccumSp(uvote_t vote);

  bool verifyPrepareAccCert(MsgPrepareAcc msg);
  bool verifyLdrPrepareAcc(MsgLdrPrepareAcc msg);
  bool verifyAcc(Accum acc);
  bool verifyPreCommitAccCert(MsgPreCommitAcc msg);

  // To create MsgPrepareAcc messages in the prepare phase
  MsgPrepareAcc createMsgPrepareAcc(Block block);
  // To create MsgPreCommitAcc messages in the pre-commit phase
  MsgPreCommitAcc createMsgPreCommitAcc(View view, Hash hash);
  // To create MsgNewViewAcc messages at the beginning of a new view
  MsgNewViewAcc createMsgNewViewAcc();

  void handleNewviewAcc(MsgNewViewAcc msg);
  void handlePrepareAcc(MsgPrepareAcc msg);
  void handleLdrPrepareAcc(MsgLdrPrepareAcc msg);
  void handlePreCommitAcc(MsgPreCommitAcc msg);

  void handle_newviewacc(MsgNewViewAcc msg, const PeerNet::conn_t &conn);
  void handle_prepareacc(MsgPrepareAcc msg, const PeerNet::conn_t &conn);
  void handle_ldrprepareacc(MsgLdrPrepareAcc msg, const PeerNet::conn_t &conn);
  void handle_precommitacc(MsgPreCommitAcc msg, const PeerNet::conn_t &conn);



  // ------------------------------------------------------------
  // Cheap&Quick
  // ------

  void executeComb(RData rdata);
  void handleEarlierMessagesComb();
  void startNewViewCombOn(Just just);
  void startNewViewComb();

  // For leaders to start preparing
  void prepareComb();
  // For leaders to start pre-committing
  void preCommitComb(RData data);
  // For leaders to start deciding
  void decideComb(RData data);

  // For backups to respond to correct MsgLdrPrepareComb messages received from leaders
  void respondToLdrPrepareComb(Block block, Accum acc);
  // For backups to respond to MsgPrepareComb messages receveid from leaders
  void respondToPrepareComb(MsgPrepareComb msg);
  // For backups to respond to MsgPreCommitComb messages receveid from leaders
  void respondToPreCommitComb(MsgPreCommitComb msg);

  Accum newviews2accComb(std::set<MsgNewViewComb> newviews);

  Accum callTEEaccumComb(Just justs[MAX_NUM_SIGNATURES]);
  Accum callTEEaccumCombSp(just_t just);
  Just callTEEsignComb();
  Just callTEEprepareComb(Hash h, Accum acc);
  Just callTEEstoreComb(Just j);

  void handleNewviewComb(MsgNewViewComb msg);
  void handlePrepareComb(MsgPrepareComb msg);
  void handleLdrPrepareComb(MsgLdrPrepareComb msg);
  void handlePreCommitComb(MsgPreCommitComb msg);

  void handle_newviewcomb(MsgNewViewComb msg, const PeerNet::conn_t &conn);
  void handle_preparecomb(MsgPrepareComb msg, const PeerNet::conn_t &conn);
  void handle_ldrpreparecomb(MsgLdrPrepareComb msg, const PeerNet::conn_t &conn);
  void handle_precommitcomb(MsgPreCommitComb msg, const PeerNet::conn_t &conn);



  // ------------------------------------------------------------
  // Free
  // ------

  void executeFree(FData data);
  void handleEarlierMessagesFree();
  void startNewViewFreeOn(FJust just);
  void startNewViewFree();

  // For leaders to start preparing
  void prepareFree();
  // For leaders to start pre-committing
  void preCommitFree(View view);
  void preCommitOnJustFree(PJust pjust);
  // For leaders to start deciding
  void decideFree(FData data);
  // to call TEEstore and record the certificate
  FVJust triggeringStoreFree(PJust pjust);

  // For backups to respond to correct MsgLdrPrepareFree messages received from leaders
  void respondToLdrPrepareFree(HAccum acc);
  // For backups to respond to MsgPrepareFree messages receveid from leaders
  void respondToPrepareFree(MsgPrepareFree msg);
  void respondToPrepareOnJustFree(PJust pjust);
  // For backups to respond to MsgPreCommitFree messages receveid from leaders
  void respondToPreCommitFree(MsgPreCommitFree msg);

  HAccum newviews2accFree(MsgNewViewFree high, std::set<MsgNewViewFree> others, Hash hash);

  MsgNewViewFree highestNewViewFree(std::set<MsgNewViewFree> *newviews);

  bool callTEEverifyFree(Auths auths, std::string s);
  bool callTEEverifyFree2(Auths auths1, std::string s1, Auths auths2, std::string s2);
  Auth callTEEauthFree(std::string s);
  Auth callTEEauthView();                          // only for the kinda ROTE version
  //Auth callTEEauthCounter(View view, View couter); // only for the kinda ROTE version
  HAccum callTEEaccumFree(FJust just, FJust justs[MAX_NUM_SIGNATURES], Hash hash);
  HAccum callTEEaccumFreeSp(ofjust_t just, Hash hash);
  Just callTEEsignFree();
  // HJust callTEEprepareFree(Hash h);
  FVJust callTEEstoreFree(PJust j);

  void handleNewviewFree(MsgNewViewFree msg);
  void handlePrepareFree(MsgPrepareFree msg);
  void handleLdrPrepareFree(HAccum acc, Block blockk);
  void handleBckPrepareFree(MsgBckPrepareFree msg);
  void handlePreCommitFree(MsgPreCommitFree msg);

  void handle_newviewfree(MsgNewViewFree msg, const PeerNet::conn_t &conn);
  void handle_preparefree(MsgPrepareFree msg, const PeerNet::conn_t &conn);
  void handle_ldrpreparefree(MsgLdrPrepareFree msg, const PeerNet::conn_t &conn);
  void handle_bckpreparefree(MsgBckPrepareFree msg, const PeerNet::conn_t &conn);
  void handle_precommitfree(MsgPreCommitFree msg, const PeerNet::conn_t &conn);

  // ------------------------------------------------------------
  // kinda ROTE - shared with FREE
  // ------

  void triggeringCounterRote(View view);

  void sendMsgCounterRote(MsgCounterRote msg, Peers recipients);
  void sendMsgEchoRote(MsgEchoRote msg, Peers recipients);
  void sendMsgAckRote(MsgAckRote msg, Peers recipients);
  void sendMsgRequestCounterRote(MsgRequestCounterRote msg, Peers recipients);
  void sendMsgReplyCounterRote(MsgReplyCounterRote msg, Peers recipients);

  void handleCounterRote(MsgCounterRote msg);
  void handleEchoRote(MsgEchoRote msg);
  void handleAckRote(MsgAckRote msg);

  void handle_counter_rote(MsgCounterRote msg, const PeerNet::conn_t &conn);
  void handle_echo_rote(MsgEchoRote msg, const PeerNet::conn_t &conn);
  void handle_ack_rote(MsgAckRote msg, const PeerNet::conn_t &conn);

  void restartFreeRote();
  void handleRequestCounterRote(MsgRequestCounterRote msg);
  void handleReplyCounterRote(MsgReplyCounterRote msg);
  void handle_request_counter_rote(MsgRequestCounterRote msg, const PeerNet::conn_t &conn);
  void handle_reply_counter_rote(MsgReplyCounterRote msg, const PeerNet::conn_t &conn);

  // ------------------------------------------------------------
  // 1/2 PHASE
  // ------

  void handleEarlierMessagesOP();

  MsgNewViewOPB genMsgNewViewOPB();
  MsgNewViewOPBB genMsgNewViewOPBB();

  OPproposal callTEEprepareOP(Hash h);
  OPstore callTEEstoreOP(OPproposal prop);
  bool callTEEverifyOP(Auths auths, std::string s);
  OPaccum callTEEaccumOp(OPstore high, OPstore justs[MAX_NUM_SIGNATURES-1]);
  OPaccum callTEEaccumOpSp(OPprepare just);
  OPvote callTEEvoteOP(Hash h);

  bool verifyPrepareOP(OPprepare cert);
  bool verifyLdrPrepareOP(MsgLdrPrepareOPA msg);
  bool verifyLdrPrepareOP(MsgLdrPrepareOPB msg);
  bool verifyLdrPrepareOP(MsgLdrPrepareOPC msg);

  void startNewViewOPA(OPprepare prep);
  void startNewViewOPB();
  void startNewViewOP(int nextView = -1);

  void executeOP(OPprepare cert);
  void preCommitOP(View v);
  void prepareOp(OPprepare prep);
  void prepareOp_debug(OPprepare prep);
  void prepareOpAcc(OPaccum acc, OPstore store, OPprepare prep);
  void prepareOpVote(OPvote vote);
  OPnvblock highestNewViewOpb(std::set<OPnvblock> *newviews);
  OPaccum newviews2accOp(OPnvblock high, std::set<OPnvcert> others);
  void prepareOpb(View v);
  void respondToLdrPrepareOP(Block block, OPproposal prop, OPcert cert);
  void respondToPreCommitOP(OPprepare cert);

  void startNewViewOnTimeoutOP();
  bool validAddOp(View v, OPaccum acc, OPnvblock nv);
  bool validOPvote(OPvote vote);

  void handleNewviewOP(OPprepare prep);
  void handleNewviewOP(MsgNewViewOPA msg);
  void handleNewviewOP(MsgNewViewOPB msg);
  void handleNewviewOP(MsgNewViewOPBB msg);
  void handlePreCommitOP(MsgPreCommitOP msg);
  void handleLdrPrepareOP(MsgLdrPrepareOPA msg);
  void handleLdrPrepareOP(MsgLdrPrepareOPB msg);
  void handleLdrPrepareOP(MsgLdrPrepareOPC msg);
  void handleBckPrepareOP(MsgBckPrepareOP msg);
  void handleLdrAddOP(MsgLdrAddOP msg);
  void handleBckAddOP(OPvote vote);

  void handle_newviewopa(MsgNewViewOPA msg, const PeerNet::conn_t &conn);
  void handle_newviewopb(MsgNewViewOPB msg, const PeerNet::conn_t &conn);
  void handle_newviewopbb(MsgNewViewOPBB msg, const PeerNet::conn_t &conn);
  void handle_precommitop(MsgPreCommitOP msg, const PeerNet::conn_t &conn);
  void handle_ldrprepareopa(MsgLdrPrepareOPA msg, const PeerNet::conn_t &conn);
  void handle_ldrprepareopb(MsgLdrPrepareOPB msg, const PeerNet::conn_t &conn);
  void handle_ldrprepareopc(MsgLdrPrepareOPC msg, const PeerNet::conn_t &conn);
  void handle_bckprepareop(MsgBckPrepareOP msg, const PeerNet::conn_t &conn);
  void handle_ldraddop(MsgLdrAddOP msg, const PeerNet::conn_t &conn);
  void handle_bckaddop(MsgBckAddOP msg, const PeerNet::conn_t &conn);


  // ------------------------------------------------------------
  // Baseline Chained
  // ------

  Just justNV;

  void startNewViewCh();

  Just callTEEsignCh();
  Just callTEEprepareCh(JBlock block, JBlock block0, JBlock block1);

  JBlock createNewBlockCh();

  Just ldrPrepareCh2just(MsgLdrPrepareCh msg);

  void tryExecuteCh(JBlock block, JBlock block0, JBlock block1);
  void voteCh(JBlock block);
  void prepareCh();
  void checkNewJustCh(RData data);
  void handleEarlierMessagesCh();

  void handleNewviewCh(MsgNewViewCh msg);
  void handlePrepareCh(MsgPrepareCh msg);
  void handleLdrPrepareCh(MsgLdrPrepareCh msg);

  void handle_newview_ch(MsgNewViewCh msg, const PeerNet::conn_t &conn);
  void handle_prepare_ch(MsgPrepareCh msg, const PeerNet::conn_t &conn);
  void handle_ldrprepare_ch(MsgLdrPrepareCh msg, const PeerNet::conn_t &conn);



  // ------------------------------------------------------------
  // Chained Cheap&Quick
  // ------

  CA caprep;

  void startNewViewChComb();

  Just callTEEsignChComb();
  Just callTEEprepareChComb(CBlock block, Hash hash);
  Accum callTEEaccumChComb(Just justs[MAX_NUM_SIGNATURES]);
  Accum callTEEaccumChCombSp(just_t just);

  CBlock createNewBlockChComb();

  Just ldrPrepareChComb2just(MsgLdrPrepareChComb msg);

  void tryExecuteChComb(CBlock block, CBlock block0);
  void voteChComb(CBlock block);
  void prepareChComb();
  void checkNewJustChComb(RData data);
  void handleEarlierMessagesChComb();
  Accum newviews2accChComb(std::set<MsgNewViewChComb> newviews);

  void handleNewviewChComb(MsgNewViewChComb msg);
  void handlePrepareChComb(MsgPrepareChComb msg);
  void handleLdrPrepareChComb(MsgLdrPrepareChComb msg);

  void handle_newview_ch_comb(MsgNewViewChComb msg, const PeerNet::conn_t &conn);
  void handle_prepare_ch_comb(MsgPrepareChComb msg, const PeerNet::conn_t &conn);
  void handle_ldrprepare_ch_comb(MsgLdrPrepareChComb msg, const PeerNet::conn_t &conn);

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

  void handle_pm_sync(MsgPmSync msg, const PeerNet::conn_t &conn);
  void handle_pm_sync_tc(MsgPmSyncTC msg, const PeerNet::conn_t &conn);
  void handle_pm_sync_vote(MsgPmSyncVote msg, const PeerNet::conn_t &conn);
  void handle_pm_sync_vote_qc(MsgPmSyncVoteQc msg, const PeerNet::conn_t &conn);

  void handlePmSync(PmSync msg);
  void handlePmSyncTC(MsgPmSyncTC qc);
  void handlePmSyncVote(PmSync msg);
  void handlePmSyncVoteQc(MsgPmSyncVoteQc qc);

  PmSync callTEEpmSync(FVJust store);
  PmSync callTEEpmSyncVote(PmSync sync);
  FVJust callTEEpmSyncEnd(PmSyncs votes);

  void sendMsgPmSync(MsgPmSync msg, Peers recipients);
  void sendMsgPmSyncTC(MsgPmSyncTC msg, Peers recipients);
  void sendMsgPmSyncVote(MsgPmSyncVote msg, Peers recipients);
  void sendMsgPmSyncVoteQc(MsgPmSyncVoteQc msg, Peers recipients);

  void handleEarlierMessagesPmSync();
  void wishToAdvanceOnPmSync(MsgPmSync msg, PID leader);
  void wishToAdvancePm();
  void startNewViewOrSyncFree(FJust just);

  void restartFreeAchilles();
  void sendMsgRestart(MsgRestart msg, Peers recipients);
  void sendMsgReplyRestart(MsgReplyRestart msg, Peers recipients);
  void handle_restart(MsgRestart msg, const PeerNet::conn_t &conn);
  void handleRestart(MsgRestart msg);
  void handle_reply_restart(MsgReplyRestart msg, const PeerNet::conn_t &conn);
  void handleReplyRestart(MsgReplyRestart msg);

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
