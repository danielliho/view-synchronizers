#ifndef LOG_H
#define LOG_H

#include <set>
#include <map>
#include <list>


#include "Just.h"
#include "Void.h"
#include "Cert.h"
#include "Message.h"
#include "RBproposal.h"


class Log {
 private:
  std::map<View,std::set<MsgNewView>> newviews;
  std::map<View,std::set<MsgPrepare>> prepares;
  std::map<View,std::set<MsgPreCommit>> precommits;
  std::map<View,std::set<MsgCommit>> commits;
  std::map<View,std::set<MsgLdrPrepare>> proposals;

  std::map<View,std::set<MsgNewViewComb>> newviewsComb;
  std::map<View,std::set<MsgPrepareComb>> preparesComb;
  std::map<View,std::set<MsgPreCommitComb>> precommitsComb;
  std::map<View,std::set<MsgLdrPrepareComb>> ldrpreparesComb;

  std::map<View,std::set<OPprepare>> newviewsOPa;
  std::map<View,std::set<OPnvblocks>> newviewsOPb;
  std::map<View,std::set<OPstore>> storesOP;
  std::map<View,std::tuple<LdrPrepareOP>> ldrpreparesOP;
  std::map<View,std::set<OPprepare>> preparesOP;
  std::map<View,std::set<OPvote>> votesOP;
  std::map<View,std::set<OPaccum>> accumsOP;

  std::map<View,std::set<MsgNewViewCh>> newviewsCh;
  std::map<View,std::set<MsgPrepareCh>> preparesCh;
  std::map<View,std::set<MsgLdrPrepareCh>> ldrpreparesCh;

  std::map<View,std::set<MsgNewViewChComb>> newviewsChComb;
  std::map<View,std::set<MsgPrepareChComb>> preparesChComb;

  std::map<Session,std::set<Sync>> syncs;                  // leader -- all received syncs
  std::map<Session,std::set<MsgSyncTC>> synctcs;           // all received sync-tcs
  std::map<SyncVote,Auths> syncvotes;                      // leader -- all received votes
  std::map<Session,std::tuple<MsgSyncVoteQc>> syncvoteqcs; // received sync-vote-qcs

  std::map<View,std::set<PmSync>> pmsyncs;                 // leader -- all received syncs
  std::map<View,std::set<MsgPmSyncTC>> pmsynctcs;             // all received sync-tcs
  std::map<View,PmSyncs> pmsyncvotes;                         // leader -- all received votes
  std::map<View,std::tuple<MsgPmSyncVoteQc>> pmsyncvoteqcs;   // received sync-vote-qcs

  std::map<View,std::set<RBnewviewAuth>>    newviewsRB;
  std::map<View,std::tuple<RBprepareAuths>> preparesRB;  // a tuple of size 0 or 1
  std::map<View,std::tuple<RBstoreAuths>>   storesRB;    // a tuple of size 0 or 1
  std::map<View,std::tuple<RBproposal>>     proposalsRB; // a tuple of size 0 or 1

 public:
  Log();

  // those return the number of signatures (0 if the msg is not from a not-yet-heard-from node)
  unsigned int storeNv(MsgNewView msg);
  unsigned int storePrep(MsgPrepare msg);
  unsigned int storePc(MsgPreCommit msg);
  unsigned int storeCom(MsgCommit msg);
  unsigned int storeProp(MsgLdrPrepare msg);

  unsigned int storeNvComb(MsgNewViewComb msg);
  unsigned int storePrepComb(MsgPrepareComb msg);
  unsigned int storePcComb(MsgPreCommitComb msg);
  unsigned int storeLdrPrepComb(MsgLdrPrepareComb msg);

  std::set<RBnewviewAuth> getNewViewRB(View view, unsigned int n);
  unsigned int storeNvRB(RBnewviewAuth msg);
  unsigned int storePropRB(RBproposal msg);
  unsigned int storePrepRB(RBprepareAuth msg);
  unsigned int storePrepsRB(RBprepareAuths msg);
  unsigned int storePcRB(RBstoreAuth msg);
  unsigned int storePcsRB(RBstoreAuths msg);
  // TODO: should be session + view
  RBprepareAuths getPrepareRB(View view);
  RBstoreAuths getPcRB(View view);
  RBproposal getPropRB(View view);

  unsigned int storeNvOp(OPprepare prep);  // from a MsgNewViewOPA
  unsigned int storeNvOp(OPnvblock newnv); // from a MsgNewViewOPB
  OPnvblocks getNvOpbs(View view);
  OPprepare getNvOpas(View view);
  unsigned int storeStoreOp(OPstore store);
  OPprepare getOPstores(View view, unsigned int n);
  unsigned int storeLdrPrepOp(LdrPrepareOP msg);
  LdrPrepareOP getLdrPrepareOp(View view);
  unsigned int storePrepareOp(OPprepare prep);
  OPprepare getOPprepare(View view);
  unsigned int storeVoteOp(OPvote vote, unsigned int* m);
  OPvote getOPvote(View view, unsigned int n);
  void storeAccumOp(OPaccum acc);
  OPaccum getAccOp(View view);

  unsigned int storeNvCh(MsgNewViewCh msg);
  unsigned int storePrepCh(MsgPrepareCh msg);
  unsigned int storeLdrPrepCh(MsgLdrPrepareCh msg);

  unsigned int storeNvChComb(MsgNewViewChComb msg);
  unsigned int storePrepChComb(MsgPrepareChComb msg);

  // finds the justification of the highest message in the 'newviews' log for view 'view'
  Just findHighestNv(View view);
  Just firstPrepare(View view);
  Just firstPrecommit(View view);
  Just firstCommit(View view);
  MsgLdrPrepare firstProposal(View view);

  // collects the signatures of the messages in the 'newviews' log for view 'view', upto 'n' signatures
  Signs getNewView(View view, unsigned int n);
  // collects the signatures of the messages in the 'proposals' log for view 'view', upto 'n' signatures
  Signs getPrepare(View view, unsigned int n);
  // collects the signatures of the messages in the 'precommits' log for view 'view', upto 'n' signatures
  Signs getPrecommit(View view, unsigned int n);
  // collects the signatures of the messages in the 'commits' log for view 'view', upto 'n' signatures
  Signs getCommit(View view, unsigned int n);

  std::set<MsgNewViewComb> getNewViewComb(View view, unsigned int n);
  Signs getPrepareComb(View view, unsigned int n);
  Signs getPrecommitComb(View view, unsigned int n);

  MsgLdrPrepareComb firstLdrPrepareComb(View view);
  MsgPrepareComb firstPrepareComb(View view);
  MsgPreCommitComb firstPrecommitComb(View view);

  std::set<MsgNewViewCh> getNewViewCh(View view, unsigned int n);
  Signs getPrepareCh(View view, unsigned int n);

  MsgLdrPrepareCh firstLdrPrepareCh(View view);
  MsgPrepareCh firstPrepareCh(View view);

  Just findHighestNvCh(View view);

  std::set<MsgNewViewChComb> getNewViewChComb(View view, unsigned int n);
  Signs getPrepareChComb(View view, unsigned int n);

  MsgPrepareChComb firstPrepareChComb(View view);

  Just findHighestNvChComb(View view);

//  unsigned int maxSync();
  unsigned int storeSync(Sync msg);
  unsigned int storeSyncTC(MsgSyncTC msg);
  unsigned int storeSyncVote(MsgSyncVote msg);
  unsigned int storeSyncVoteQc(MsgSyncVoteQc msg);

  std::set<Sync> getSync(Session session);
  bool getSyncTcFrom(Session session, PID id);
  bool newSyncTc(MsgSyncTC msg);
  std::set<MsgSyncTC> getSyncTcs(Session session);
  Auths getSyncVote(SyncVote vote, unsigned int n);
  MsgSyncVoteQc getSyncVoteQc(Session session);

  unsigned int storePmSync(PmSync sync);
  unsigned int storePmSyncTC(MsgPmSyncTC msg);
  unsigned int storePmSyncVote(PmSync vote);
  unsigned int storePmSyncVoteQc(MsgPmSyncVoteQc msg);

  std::set<PmSync> getPmSync(View view);
  Auths getPmSyncVote(PmSync vote, unsigned int n);
  bool newPmSyncTc(MsgPmSyncTC msg);
  MsgPmSyncVoteQc getPmSyncVoteQc(View view);
  std::set<MsgPmSyncTC> getPmSyncTcs(View view);

/*
  unsigned int storeJoinWish(MsgJoinWish msg);
  std::list<MsgJoinWish> getJoinWish(unsigned int n);

  bool storeOwnJoinVote(MsgJoinVote msg);
  bool storedOwnJoinVote(View v);
  MsgJoinVote getOwnJoinVote(View v);
*/

  // generates a string to pretty print logs
  std::string prettyPrint();
  std::string printSyncVotes();
};


#endif
