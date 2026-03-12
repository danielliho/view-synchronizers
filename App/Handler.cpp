#include <set>
//#include <algorithm>
#include <mutex>
#include <iostream>
#include <fstream>
#include <thread>
#include <random>
#include <string>
#include <cstring>
#include <mutex>

#include <unistd.h>
#include <stdio.h>
#include <sys/socket.h>
#include <stdlib.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#include <openssl/pem.h>
#include <openssl/rsa.h>
#include <openssl/rand.h>

#include "Handler.h"


// To stop the processes once they have delivered enough messages
// - deprecated as processes are now stopped from the Python script
bool hardStop = false;

std::mutex mu_trans;
std::mutex mu_handle;

Time startTime = std::chrono::steady_clock::now();
Time startView = std::chrono::steady_clock::now();
Time timerTime = std::chrono::steady_clock::now();
std::string statsVals;             // Throuput + latency + handle + crypto
std::string statsStart;            // starting to record the stats
std::string statsDone;             // done recording the stats
std::string statsTimes;            // records all times for all views

Time curTime;

Stats stats;                   // To collect statistics


// To generate uniformly distributed numbers in [0,1]
std::random_device                  rand_dev;
std::mt19937                        generator(rand_dev());
std::uniform_int_distribution<int>  distr(0, 1);


unsigned int Handler::getLeaderOf(View v) { return (v % this->total); }

unsigned int Handler::getCurrentLeader() { return getLeaderOf(this->view); }

bool Handler::amLeaderOf(View v) { return (this->myid == getLeaderOf(v)); }

bool Handler::amCurrentLeader() { return (this->myid == getCurrentLeader()); }

std::string Handler::amCurrentLeaderStr() {
  if (amCurrentLeader()) { return "L"; }
  return "B";
}


std::string Handler::nfo() {
  return ("[" + std::to_string(this->myid) + amCurrentLeaderStr() + "]"
          + "{s" +  std::to_string(this->session)
          + ",v" +  std::to_string(this->view) + "}");
}


// Athena-only mode keeps SGX trusted components path.




// ------------------------------------
// Converts between classes and simpler structures used in enclaves
//
// stores [hash] in [h]
void setHash(Hash hash, hash_t *h) {
  h->set=hash.getSet();
  std::copy_n(hash.getHash(), SHA256_DIGEST_LENGTH, std::begin(h->hash));
  //memcpy(h->hash,hash.getHash(),SHA256_DIGEST_LENGTH);
}


void setPayload(std::string s, payload_t *p) {
  p->size=s.size();
  memcpy(p->data,s.c_str(),s.size()); // MAX_SIZE_PAYLOAD
}


// stores [rdata] in [d]
void setRData(RData data, rdata_t *d) {
  // proph
  setHash(data.getProph(),&(d->proph));
  // propv
  d->propv=data.getPropv();
  // justh
  setHash(data.getJusth(),&(d->justh));
  // justv
  d->justv=data.getJustv();
  // phase
  d->phase=data.getPhase();
}


// stores [data] in [d]
void setFData(FData data, fdata_t *d) {
  // justj
  setHash(data.getJusth(),&(d->justh));
  // justv
  d->justv=data.getJustv();
  // view
  d->view=data.getView();
}

// stores 'sign' in 's'
void setSign(Sign sign, sign_t *s) {
  s->set=sign.isSet();
  s->signer=sign.getSigner();
  memcpy(s->sign,sign.getSign(),SIGN_LEN);
}

// stores [signs] in [s]
void setSigns(Signs signs, signs_t *s) {
  s->size=signs.getSize();
  for (int i = 0; i < MAX_NUM_SIGNATURES; i++) {
    setSign(signs.get(i),&(s->signs[i]));
  }
}

// stores [auth] in [a]
void setAuth(Auth auth, auth_t *a) {
  a->id=auth.getId();
  setHash(auth.getHash(),&(a->hash));
}

// stores [auths] in [s]
void setAuths(Auths auths, auths_t *s) {
  s->size=auths.getSize();
  for (int i = 0; i < MAX_NUM_SIGNATURES; i++) {
    setAuth(auths.get(i),&(s->auths[i]));
  }
}

// stores [just] in [j]
void setJust(Just just, just_t *j) {
  // ------ SET ------
  j->set=just.isSet();
  // ------ RDATA ------
  setRData(just.getRData(),&(j->rdata));
  // ------ SIGNS ------
  setSigns(just.getSigns(),&(j->signs));
}

// stores [just] in [j]
void setOneJust(Just just, onejust_t *j) {
  // ------ SET ------
  j->set=just.isSet();
  // ------ RDATA ------
  setRData(just.getRData(),&(j->rdata));
  // ------ SIGNS ------
  // we only store the first signature, as we here only care about this one
  setSign(just.getSigns().get(0),&(j->sign));
}

void setOneJusts(Just justs[MAX_NUM_SIGNATURES], onejusts_t *js) {
  for (int i = 0; i < MAX_NUM_SIGNATURES; i++) {
    setOneJust(justs[i],&(js->justs[i]));
  }
}

// stores [just] in [j]
void setFVJust(FVJust just, fvjust_t *j) {
  // ------ SET ------
  j->set=just.isSet();
  // ------ RDATA ------
  setFData(just.getData(),&(j->data));
  // ------ AUTH1 ------
  setAuth(just.getAuth1(),&(j->auth1));
  // ------ AUTH2 ------
  setAuth(just.getAuth2(),&(j->auth1));
}

// stores [just] in [j]
void setOPproposal(OPproposal just, opproposal_t *j) {
  // ------ HASH ------
  setHash(just.getHash(),&(j->hash));
  // ------ VIEW ------
  j->view=just.getView();
  // ------ AUTH ------
  setAuth(just.getAuth(),&(j->auth));
}

// stores [just] in [j]
void setOPprepare(OPprepare just, opprepare_t *j) {
  // ------ VIEW ------
  j->view=just.getView();
  // ------ HASH ------
  setHash(just.getHash(),&(j->hash));
  // ------ V ------
  j->v=just.getV();
  // ------ AUTHS ------
  setAuths(just.getAuths(),&(j->auths));
}

// stores [just] in [j]
void setOPstore(OPstore just, opstore_t *j) {
  // ------ VIEW ------
  j->view=just.getView();
  // ------ HASH ------
  setHash(just.getHash(),&(j->hash));
  // ------ V ------
  j->v=just.getV();
  // ------ AUTHS ------
  setAuth(just.getAuth(),&(j->auth));
}

void setOPstores(OPstore justs[MAX_NUM_SIGNATURES-1], opstores_t *js) {
  for (int i = 0; i < MAX_NUM_SIGNATURES-1; i++) {
    setOPstore(justs[i],&(js->stores[i]));
  }
}

// stores [prep] in [p]
void setRBprepare(RBprepare prep, rbprepare_t *p) {
  // ------ SESSION ------
  p->session=prep.getSession();
  // ------ VIEW ------
  p->view=prep.getView();
  // ------ HASH ------
  setHash(prep.getHash(),&(p->hash));
}

// stores [prep] in [p]
void setRBprepareAuth(RBprepareAuth prep, rbprepare_auth_t *p) {
  // ------ PREPARE ------
  setRBprepare(prep.getPrepare(),&(p->prep));
  // ------ AUTH ------
  setAuth(prep.getAuth(),&(p->auth));
}

// stores [prep] in [p]
void setRBprepareAuths(RBprepareAuths prep, rbprepare_auths_t *p) {
  // ------ PREPARE ------
  setRBprepare(prep.getPrepare(),&(p->prep));
  // ------ AUTH ------
  setAuths(prep.getAuths(),&(p->auths));
}

// stores [newview] in [p]
void setRBnewview(RBnewview newview, rbnewview_t *p) {
  // ------ SESSION ------
  p->session=newview.getSession();
  // ------ VIEW ------
  p->view=newview.getView();
  // ------ PREPV ------
  p->prepv=newview.getPrepv();
  // ------ HASH ------
  setHash(newview.getHash(),&(p->hash));
}

// stores [newview] in [p]
void setRBnewviewAuth(RBnewviewAuth newview, rbnewview_auth_t *p) {
  // ------ NEWVIEW ------
  setRBnewview(newview.getNewview(),&(p->newview));
  // ------ AUTH ------
  setAuth(newview.getAuth(),&(p->auth));
}

// stores [newviews] in [p]
void setRBnewviews(std::set<RBnewviewAuth> newviews, rbnewviews_t *p) {
  int i = 0;
  for (std::set<RBnewviewAuth>::iterator it = newviews.begin();
       it != newviews.end() && i < MAX_NUM_SIGNATURES-1;
       ++it, i++) {
    setRBnewviewAuth((RBnewviewAuth)*it,&(p->newviews[i]));
  }
}

// stores [store] in [p]
void setRBstore(RBstore store, rbstore_t *p) {
  // ------ SESSION ------
  p->session=store.getSession();
  // ------ VIEW ------
  p->view=store.getView();
  // ------ HASH ------
  setHash(store.getHash(),&(p->hash));
}

// stores [store] in [p]
void setRBstoreAuth(RBstoreAuth store, rbstore_auth_t *p) {
  // ------ STORE ------
  setRBstore(store.getStore(),&(p->store));
  // ------ AUTH ------
  setAuth(store.getAuth(),&(p->auth));
}

// stores [store] in [p]
void setRBstoreAuths(RBstoreAuths store, rbstore_auths_t *p) {
  // ------ STORE ------
  setRBstore(store.getStore(),&(p->store));
  // ------ AUTH ------
  setAuths(store.getAuths(),&(p->auths));
}

// stores [acc] in [p]
void setRBaccumSync(RBaccumSync acc, rbaccum_sync_t *p) {
  // ------ SESSION ------
  p->session=acc.getSession();
  // ------ VIEW ------
  p->view=acc.getView();
  // ------ HASH ------
  setHash(acc.getHash(),&(p->hash));
}

// stores [acc] in [p]
void setRBaccumSyncAuth(RBaccumSyncAuth acc, rbaccum_sync_auth_t *p) {
  // ------ ACCUM ------
  setRBaccumSync(acc.getAcc(),&(p->acc));
  // ------ AUTH ------
  setAuth(acc.getAuth(),&(p->auth));
}

// loads a Hash from [h]
Hash getHash(hash_t *h) {
  return Hash(h->set,h->hash);
}

Sign getSign(sign_t *s) {
  return Sign(s->set,s->signer,s->sign);
}

FData getFData (fdata_t *d) {
  Hash   justh = getHash(&(d->justh));
  View   justv = d->justv;
  View   view  = d->view;
  FData  data(justh,justv,view);
  return data;
}

RData getRData (rdata_t *d) {
  Hash   proph = getHash(&(d->proph));
  View   propv = d->propv;
  Hash   justh = getHash(&(d->justh));
  View   justv = d->justv;
  Phase1 phase = (Phase1)d->phase;
  RData  data(proph,propv,justh,justv,phase);
  return data;
}

// loads a Just from [j]
Just getJust(just_t *j) {
  RData rdata = getRData(&(j->rdata));
  Sign  a[MAX_NUM_SIGNATURES];
  for (int i = 0; i < MAX_NUM_SIGNATURES; i++) {
    a[i]=Sign(j->signs.signs[i].set,j->signs.signs[i].signer,j->signs.signs[i].sign);
  }
  Signs signs(j->signs.size,a);
  return Just((bool)j->set,rdata,signs);
}

Auth getAuth(auth_t *a) {
  return Auth(a->id,getHash(&a->hash));
}

// loads a HJust from [j]
HJust getHJust(hjust_t *j) {
  Hash   hash = getHash(&(j->hash));
  View   view = j->view;
  Auth   auth = getAuth(&(j->auth));
  return HJust((bool)j->set,hash,view,auth);
}

// loads a FVJust from [j]
FVJust getFVJust(fvjust_t *j) {
  bool   set   = j->set;
  FData  data  = getFData(&(j->data));
  Auth   auth1 = getAuth(&(j->auth1));
  Auth   auth2 = getAuth(&(j->auth2));
  return FVJust(set,data,auth1,auth2);
}

// loads a OPstore from [j]
OPstore getOPstore(opstore_t *j) {
  View   view = j->view;
  Hash   hash = getHash(&(j->hash));
  View   v    = j->v;
  Auth   auth = getAuth(&(j->auth));
  return OPstore(view,hash,v,auth);
}

Auths getAuths(auths_t *j) {
  Auth  a[MAX_NUM_SIGNATURES];
  for (int i = 0; i < MAX_NUM_SIGNATURES; i++) {
    a[i]=getAuth(&(j->auths[i]));
  }
  return Auths(j->size,a);
}


// loads an OPvote from [j]
OPvote getOPvote(opvote_t *j) {
  Hash   hash  = getHash(&(j->hash));
  View   view  = j->view;
  Auths  auths = getAuths(&(j->auths));
  return OPvote(hash,view,auths);
}

// loads an OPproposal from [j]
OPproposal getOPproposal(opproposal_t *j) {
  Hash    hash  = getHash(&(j->hash));
  View    view  = j->view;
  Auth    auth  = getAuth(&(j->auth));
  return OPproposal(hash,view,auth);
}

// loads an OPaccum from [j]
OPaccum getOPaccum(opaccum_t *j) {
  bool    set  = j->set;
  NVkind  kind = j->kind;
  View    view = j->view;
  Hash    hash = getHash(&(j->hash));
  unsigned int size = j->size;
  Auth    auth = getAuth(&(j->auth));
  return OPaccum(set,kind,view,hash,size,auth);
}

// loads a Accum from [a]
Accum getAccum(accum_t *a) {
  bool set   = a->set;
  View view  = a->view;
  View prepv = a->prepv;
  Hash hash  = getHash(&(a->hash));
  unsigned int size = a->size;
  Sign sign  = Sign(a->sign.set,a->sign.signer,a->sign.sign);
  return Accum(set,view,prepv,hash,size,sign);
}

// stores [acc] in [a]
void setAccum(Accum acc, accum_t *a) {
  // ------ SET ------
  a->set=acc.isSet();
  // ------ VIEW ------
  a->view=acc.getView();
  // ------ PREPV ------
  a->prepv=acc.getPrepv();
  // ------ PREPH ------
  setHash(acc.getPreph(),&(a->hash));
  //a->hash.set=acc.getPreph().getSet();
  //memcpy(a->hash.hash,acc.getPreph().getHash(),SHA256_DIGEST_LENGTH);
  // ------ SIZE ------
  a->size=acc.getSize();
  // ------ SIGN ------
  setSign(acc.getSign(),&(a->sign));
}

void setJBlock(JBlock block, jblock_t *b) {
  b->set=block.isSet();
  b->executed=block.isExecuted();
  b->view=block.getView();
  setJust(block.getJust(),&(b->just));
  b->size=block.getSize();
  for (int i = 0; i < MAX_NUM_TRANSACTIONS; i++) {
    Transaction *t = block.getTransactions();
    b->trans[i].clientid=t[i].getCid();
    b->trans[i].transid=t[i].getTid();
    memcpy(b->trans[i].data,t[i].getData(),PAYLOAD_SIZE);
  }
}

void setCert(Cert cert, cert_t *c) {
  c->view=cert.getView();
  setHash(cert.getHash(),&(c->hash));
  setSigns(cert.getSigns(),&(c->signs));
}

// loads a Join from w
Join getJoin(join_t *w) {
  Session session = w->session;
  Hash    nonce   = getHash(&(w->nonce));
  Auth    auth    = getAuth(&(w->auth));
  return Join(session,nonce,auth);
}

// loads a Sync from w
Sync getSync(sync_t *w) {
  Session session = w->session;
  View    view    = w->view;
  Hash    hash    = getHash(&(w->hash));
  Auth    auth    = getAuth(&(w->auth));
  return Sync(session,view,hash,auth);
}

// loads a PmSync from w
PmSync getPmSync(pm_sync_t *w) {
  View view  = w->view;
  Hash hash = getHash(&(w->hash));
  Auth auth  = getAuth(&(w->auth));
  return PmSync(view,hash,auth);
}

// loads a INonce from w
INonce getINonce(inonce_t *w) {
  PID id     = w->id;
  Hash nonce = getHash(&(w->nonce));
  return INonce(id,nonce);
}

INonces getINonces(inonces_t *j) {
  INonces nonces;
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    INonce nonce = getINonce(&(j->inonces[i]));
    if (nonce.getNonce().getSet()) { nonces.set(nonce); }
  }
  return nonces;
}

// loads a SyncVote from w
SyncVote getSyncVote(sync_vote_t *w) {
  Session session = w->session;
  View    view    = w->view;
  Hash    hash    = getHash(&(w->hash));
  INonces joins   = getINonces(&(w->joins));
  return SyncVote(session,view,hash,joins);
}

// loads a SyncVote from w
SyncVote getSpSyncVote(sp_sync_vote_t *w) {
  Session session = w->session;
  View    view    = w->view;
  Hash    hash    = getHash(&(w->hash));
  return SyncVote(session,view,hash,INonces());
}

// loads a SyncVoteAuth from w
SyncVoteAuth getSyncVoteAuth(sync_vote_auth_t *w) {
  SyncVote vote = getSyncVote(&(w->vote));
  Auth     auth = getAuth(&(w->auth));
  return SyncVoteAuth(vote,auth);
}

// loads a SyncVoteAuth from w
SyncVoteAuth getSpSyncVoteAuth(sp_sync_vote_auth_t *w) {
  SyncVote vote = getSpSyncVote(&(w->vote));
  Auth     auth = getAuth(&(w->auth));
  return SyncVoteAuth(vote,auth);
}

// stores [inonce] in [a]
void setINonce(INonce inonce, inonce_t *a) {
  a->id=inonce.getId();
  setHash(inonce.getNonce(),&(a->nonce));
}

// stores [inonces] in [s]
void setINonces(INonces inonces, inonces_t *s) {
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    setINonce(inonces.get(i),&(s->inonces[i]));
  }
}

// stores [vote] in [p]
void setSyncVote(SyncVote vote, sync_vote_t *p) {
  // ------ SESSION ------
  p->session=vote.getSession();
  // ------ VIEW ------
  p->view=vote.getView();
  // ------ HASH ------
  setHash(vote.getBlock(),&(p->hash));
  // ------ INONCES ------
  setINonces(vote.getJoins(),&(p->joins));
}

// stores [vote] in [p]
void setSpSyncVote(SyncVote vote, sp_sync_vote_t *p) {
  // ------ SESSION ------
  p->session=vote.getSession();
  // ------ VIEW ------
  p->view=vote.getView();
  // ------ Hash ------
  setHash(vote.getBlock(),&(p->hash));
}

// stores [vote] in [p]
void setSyncVoteAuth(SyncVoteAuth vote, sync_vote_auth_t *p) {
  // ------ VOTE ------
  setSyncVote(vote.getVote(),&(p->vote));
  // ------ AUTH ------
  setAuth(vote.getAuth(),&(p->auth));
}

// stores [vote] in [p]
void setSpSyncVoteAuth(SyncVoteAuth vote, sp_sync_vote_auth_t *p) {
  // ------ VOTE ------
  setSpSyncVote(vote.getVote(),&(p->vote));
  // ------ AUTH ------
  setAuth(vote.getAuth(),&(p->auth));
}

// stores [vote] in [p]
void setSyncVoteAuths(SyncVoteAuths vote, sync_vote_auths_t *p) {
  // ------ VOTE ------
  setSyncVote(vote.getVote(),&(p->vote));
  // ------ AUTH ------
  setAuths(vote.getAuths(),&(p->auths));
}

// stores [vote] in [p]
void setSpSyncVoteAuths(SyncVoteAuths vote, sp_sync_vote_auths_t *p) {
  // ------ VOTE ------
  setSpSyncVote(vote.getVote(),&(p->vote));
  // ------ AUTH ------
  setAuths(vote.getAuths(),&(p->auths));
}

/*
// stores 'wishes' in 'qc'
void setJoinWishQc(MsgJoinWishQc msg, join_wish_qc_t *qc) {
  // ------ VIEW ------
  qc->view=msg.view;
  // ------ SIZE ------
  qc->size=msg.wishes.getSize();
  // ------ WISHES ------
  for (int i = 0; i < qc->size; i++) {
    qc->wishes[i].view = msg.wishes.get(i).getView();
    setHash(msg.wishes.get(i).getHash(),&(qc->wishes[i].hash));
    setAuth(msg.wishes.get(i).getAuth(),&(qc->wishes[i].auth));
  }
}
*/

Views getViews(views_t *views) {
  return Views(views->views);
}

/*
VJoins getVJoins(vjoins_t *vjoins) {
  return VJoins(vjoins->from,vjoins->to,getJoins(&(vjoins->joins)),getViews(&(vjoins->views)));
}

MsgJoinVote getJoinVote(join_vote_t *v) {
  VJoins vjoins = getVJoins(&(v->vjoins));
  Auth auth = getAuth(&(v->auth));
  return MsgJoinVote(vjoins,auth);
}
*/

void setJoin(Join join, join_t *j) {
  j->session = join.getSession();
  setHash(join.getNonce(),&(j->nonce));
  setAuth(join.getAuth(),&(j->auth));
}

void setSync(Sync sync, sync_t *j) {
  j->session = sync.getSession();
  j->view = sync.getView();
  setHash(sync.getBlock(),&(j->hash));
  setAuth(sync.getAuth(),&(j->auth));
}

void setSyncs(std::set<Sync> syncs, syncs_t *p) {
  int i = 0;
  for (std::set<Sync>::iterator it = syncs.begin();
       it != syncs.end() && i < MAX_NUM_SIGNATURES-1;
       ++it, i++) {
    setSync((Sync)*it,&(p->syncs[i]));
  }
}

void setPmSync(PmSync sync, pm_sync_t *j) {
  j->view = sync.getView();
  setHash(sync.getBlock(),&(j->hash));
  setAuth(sync.getAuth(),&(j->auth));
}

void setPmSyncs(PmSyncs syncs, pm_syncs_t *j) {
  j->view = syncs.getView();
  setHash(syncs.getBlock(),&(j->hash));
  setAuths(syncs.getAuths(),&(j->auths));
}

// stores 'views' in 'v'
void setViews(Views views, views_t *v) {
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    v->views[i] = views.get(i);
  }
}

// stores 'joins' in 'v'
void setJoins(Joins joins, joins_t *v) {
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    setJoin(joins.get(i),&(v->joins[i]));
  }
}

/*
// stores 'jvoins' in 'j'
void setVJoins(VJoins vjoins, vjoins_t *j) {
  j->from = vjoins.getFrom();
  j->to   = vjoins.getTo();
  setJoins(vjoins.getJoins(),&(j->joins));
  setViews(vjoins.getViews(),&(j->views));
}

// stores 'votes' in 'qc'
void setJoinVoteQc(MsgJoinVoteQc msg, join_vote_qc_t *qc) {
  setVJoins(msg.vjoins,&(qc->vjoins));
  setAuths(msg.auths,&(qc->auths));
}
*/

// loads a RBprepare from p
RBprepare getRBprepare(rbprepare_t *p) {
  Session session = p->session;
  View view       = p->view;
  Hash hash       = getHash(&(p->hash));
  return RBprepare(session,view,hash);
}

// loads a RBprepareAuth from p
RBprepareAuth getRBprepareAuth(rbprepare_auth_t *p) {
  RBprepare prep = getRBprepare(&(p->prep));
  Auth auth      = getAuth(&(p->auth));
  return RBprepareAuth(prep,auth);
}

// loads a RBstore from p
RBstore getRBstore(rbstore_t *p) {
  Session session = p->session;
  View view       = p->view;
  Hash hash       = getHash(&(p->hash));
  return RBstore(session,view,hash);
}

// loads a RBstoreAuth from p
RBstoreAuth getRBstoreAuth(rbstore_auth_t *p) {
  RBstore store = getRBstore(&(p->store));
  Auth auth     = getAuth(&(p->auth));
  return RBstoreAuth(store,auth);
}

// loads a RBnewview from p
RBnewview getRBnewview(rbnewview_t *p) {
  Session session = p->session;
  View view       = p->view;
  View prepv      = p->prepv;
  Hash hash       = getHash(&(p->hash));
  return RBnewview(session,view,prepv,hash);
}

// loads a RBnewviewAuth from p
RBnewviewAuth getRBnewviewAuth(rbnewview_auth_t *p) {
  RBnewview newview = getRBnewview(&(p->newview));
  Auth auth         = getAuth(&(p->auth));
  return RBnewviewAuth(newview,auth);
}

// loads a RBaccumNv from p
RBaccumNv getRBaccumNv(rbaccum_nv_t *p) {
  Session session = p->session;
  View view       = p->view;
  View prepv      = p->prepv;
  Hash hash       = getHash(&(p->hash));
  return RBaccumNv(session,view,prepv,hash);
}

// loads a RBaccumNvAuth from p
RBaccumNvAuth getRBaccumNvAuth(rbaccum_nv_auth_t *p) {
  RBaccumNv acc = getRBaccumNv(&(p->acc));
  Auth auth     = getAuth(&(p->auth));
  return RBaccumNvAuth(acc,auth);
}

// loads a RBaccumSync from p
RBaccumSync getRBaccumSync(rbaccum_sync_t *p) {
  Session session = p->session;
  View view       = p->view;
  Hash hash       = getHash(&(p->hash));
  return RBaccumSync(session,view,hash);
}

// loads a RBaccumSyncAuth from p
RBaccumSyncAuth getRBaccumSyncAuth(rbaccum_sync_auth_t *p) {
  RBaccumSync acc = getRBaccumSync(&(p->acc));
  Auth auth       = getAuth(&(p->auth));
  return RBaccumSyncAuth(acc,auth);
}

// ------------------------------------




// ------------------------------------
// SGX related stuff
#if defined(BASIC_ROLL)
/* Global EID shared by multiple threads */
sgx_enclave_id_t global_eid = 0;

// OCall implementations
void ocall_print(const char* str) { printf("%s\n", str); }
//void ocall_load_private_key(PID *id, KEY *priv) { kf.loadPrivateKey(*id, priv); }
//void ocall_load_public_key(PID *id, KEY *pub) { kf.loadPublicKey(*id, pub); }
void ocall_test(KEY *key) {
  std::string text = "foo";
  Sign sign(*key,0,text);
  std::cout << "OCALL-TEST:signed" << std::endl;
}

void ocall_setCtime() {
  curTime = std::chrono::steady_clock::now();
}

void ocall_recCVtime() {
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - curTime).count();
  //std::cout << KBLU << stats.getId() << "-stats-A:" << stats.getCryptoVerifNum() << KNRM << std::endl;
  stats.addCryptoVerifTime(time);
  //std::cout << KBLU << stats.getId() << "-stats-B:" << stats.getCryptoVerifNum() << KNRM << std::endl;
}

void ocall_recCStime() {
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - curTime).count();
  stats.addCryptoSignTime(time);
}


int Handler::initializeSGX() {
  // Initializing enclave
  if (initialize_enclave(&global_eid, "enclave.token", "enclave.signed.so") < 0) {
    std::cout << nfo() << "Failed to initialize enclave" << std::endl;
    return 1;
  }
  if (DEBUG) std::cout << KBLU << nfo() << "initialized enclave" << KNRM << std::endl;

  // Initializing variables (for simplicity)
  std::set<PID> pids = this->nodes.getIds();
  //pids.erase(this->myid);
  unsigned int num = pids.size();
  pids_t others;
  others.num_nodes=num;
  unsigned int i = 0;
  for (std::set<PID>::iterator it = pids.begin(); it != pids.end(); ++it, i++) {
    //std::cout << "adding to list of other nodes:" << *it << std::endl;
    others.pids[i]=*it;
  }

  sgx_status_t ret, status;
  rbstore_auth_t jout;
  status = TEEinitializeRB(global_eid, &ret, &(this->myid), &jout);
  this->lastRBstore = getRBstoreAuth(&jout);
  if (DEBUG1) std::cout << KBLU << nfo() << "enclave variables are initialized" << KNRM << std::endl;

  return 0;
}
#endif
// ------------------------------------



void Handler::startNewViewOnTimeout() {
  // TODO: start a new-view
  //if (DEBUG1) std::cout << KRED << nfo() << "TODO-startNewViewOnTimeout" << KNRM << std::endl;
  //exit(0);
  if (!this->rejoining) { // only nodes that are not rejoining participate
    if (this->synchronizing) {
      if (this->syncAttempts < this->qsize) {
        Session s = this->session+1;
        PID firstLeader = getLeaderOf(s);
        PID oldLeader   = (firstLeader + this->syncAttempts - 1) % this->total;
        PID newLeader   = (firstLeader + this->syncAttempts) % this->total;
        this->syncAttempts++;

        //Joins joins = getPreparedJoins(this->lastRBstore.getStore().getSession(),this->lastRBstore.getStore().getView());

        while (this->agreedJoins.in(newLeader) || this->receivedJoins.in(newLeader)) {
          PID leader = (newLeader + 1) % this->total;
          if (DEBUG1W) std::cout << KLRED << nfo() << "potential leader (" << newLeader << ")"
                                 << " is restarting, moving on to the next one (" << leader << ")"
                                 << KNRM << std::endl;
          newLeader = leader;
        }

        if (DEBUG1W) std::cout << KRED << nfo() << "TODO - timed-out while synchronizing"
                              << " (attempt=" << this->syncAttempts << ") with leaders:"
                              << " first-leader?=" << firstLeader
                              << " old-leader?="   << oldLeader
                              << " new-leader="    << newLeader
                              << KNRM
                              << std::endl;

        // if (this->agreedJoins.in(newLeader)) {
        //   if (DEBUG1) { std::cout << KLGRN << nfo() << "new synchronization leader (" << newLeader << ")"
        //                           << " is known to be restarting and can be skipped"
        //                           << KNRM << std::endl; }

        //   // TODO: while/for loop instead!
        //   startNewViewOnTimeout();

        // } else {

        // TODO - This is a very simple case of timeouts for now.
        std::set<Sync> syncs = this->log.getSync(s);
        if (syncs.size() > 0) {
          std::set<Sync>::iterator it=syncs.begin();
          Sync someSync = (Sync)*it; // 1st one
          wishToAdvanceOnSync(someSync,newLeader);
        } else {
          if (DEBUG0) std::cout << KRED << nfo() << "FAILED: timed-out while synchronizing -- no previous sync recorded" << KNRM << std::endl;
          if (DEBUG0) std::cout << KRED << nfo() << "EXIT!(0)" << KNRM << std::endl;
          exit(0);
        }
      } else {
        if (DEBUG0) std::cout << KRED << nfo() << "FAILED: timed-out while synchronizing -- too many attempts: " << this->syncAttempts << KNRM << std::endl;
        if (DEBUG0) std::cout << KRED << nfo() << "EXIT!(1)" << KNRM << std::endl;
        exit(0);
      }
    } else {
      // Not synchronizing
      PID oldLeader = getLeaderOf(this->view);
      PID newLeader = getLeaderOf(this->view+1);
      if (DEBUG1W) std::cout << KRED << nfo() << "starting new view on timeout -- leaders: " << oldLeader << " -> " << newLeader << KNRM << std::endl;
      // TODO: Check that this->lastRBstore is for the current session and prepv
      // TODO: Remove this check. This is just to check that nodes do not timeout too much
      if (oldLeader < this->numJoiners) {
        // timed-out most likely due to the fact that the old leader was a rejoiner
        startNewViewOrSyncRB(this->lastRBstore);
      } else {
        if (DEBUG0) std::cout << KRED << nfo() << "FAILURE? not sure why a timeout, old leader (" << oldLeader << ") is not a rejoiner"
                              << KNRM << std::endl;
        //if (DEBUG0) std::cout << KRED << nfo() << "EXIT!" << KNRM << std::endl;
        //exit(0);
        startNewViewOrSyncRB(this->lastRBstore);
      }
    }
  }
}



const uint8_t MsgNewViewRB::opcode;
const uint8_t MsgLdrPrepareRB::opcode;
const uint8_t MsgBckPrepareRB::opcode;
const uint8_t MsgLdrPreCommitRB::opcode;
const uint8_t MsgBckPreCommitRB::opcode;
const uint8_t MsgDecideRB::opcode;
const uint8_t MsgJoin::opcode;
const uint8_t MsgSync::opcode;
const uint8_t MsgSyncTC::opcode;
const uint8_t MsgSyncVote::opcode;
const uint8_t MsgSyncVoteQc::opcode;

const uint8_t MsgTransaction::opcode;
const uint8_t MsgReply::opcode;
const uint8_t MsgStart::opcode;
//const uint8_t MsgStop::opcode;



Handler::Handler(KeysFun k,
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
                 ClientNet::Config cconf) : pnet(pec,pconf), cnet(cec,cconf) {
  this->myid         = id;
  this->initTimeout  = timeout;
  this->timeout      = timeout;
  this->timeoutMul   = timeoutMul;
  this->timeoutDiv   = timeoutDiv;
  this->opdist       = opdist;
  this->numFaults    = numFaults;
  this->total        = (constFactor*this->numFaults)+1;
  this->qsize        = this->total-this->numFaults;
  this->nodes        = nodes;
  this->priv         = priv;
  this->maxViews     = maxViews;
  this->syncPeriod   = syncPeriod;
  this->joinPeriod   = joinPeriod;
  this->numJoiners   = numJoiners;
  this->quant1       = quant1;
  this->quant2       = quant2;
  this->skip         = skip;
  this->kf           = k;

  // further initialization of variables
  this->agreedJoins.reset();
  this->receivedJoins = Joins();
  for (int i = 0; i < MAX_NUM_NODES; i++) { this->sessions[i] = 0; }

  if (DEBUG1) { std::cout << KBLU << nfo() << "starting handler" << KNRM << std::endl; }
  if (DEBUG1) { std::cout << KBLU << nfo() << "qsize=" << this->qsize << KNRM << std::endl; }

  // Trusted Functions
  if (DEBUG0) { std::cout << KBLU << nfo() << "initializing TEE" << KNRM << std::endl; }
  initializeSGX();
  if (DEBUG0) { std::cout << KBLU << nfo() << "initialized TEE" << KNRM << std::endl; }
  //getStarted();


  // -- Salticidae
  //rep_tcall = new salticidae::ThreadCall(ec);
  req_tcall = new salticidae::ThreadCall(cec);
  // the client event context handles replies through the 'rep_queue' queue
  rep_queue.reg_handler(cec, [this](rep_queue_t &q) {
                               std::pair<TID,CID> p;
                               while (q.try_dequeue(p)) {
                                 TID tid = p.first;
                                 CID cid = p.second;
                                 Clients::iterator cit = this->clients.find(cid);
                                 if (cit != this->clients.end()) {
                                   ClientNfo cnfo = cit->second;
                                   MsgReply reply(tid);
                                   ClientNet::conn_t recipient = std::get<3>(cnfo);
                                   if (DEBUG1) std::cout << KBLU << nfo() << "sending reply to " << cid << ":" << reply.prettyPrint() << KNRM << std::endl;
                                   try {
                                     this->cnet.send_msg(reply,recipient);
                                     (this->clients)[cid]=std::make_tuple(std::get<0>(cnfo),std::get<1>(cnfo),std::get<2>(cnfo)+1,std::get<3>(cnfo));
                                   } catch(std::exception &err) {
                                     if (DEBUG0) { std::cout << KBLU << nfo() << "couldn't send reply to " << cid << ":" << reply.prettyPrint() << "; " << err.what() << KNRM << std::endl; }
                                   }
                                 } else {
                                   if (DEBUG0) { std::cout << KBLU << nfo() << "couldn't reply to unknown client: " << cid << KNRM << std::endl; }
                                 }
                               }
                               return false;
                             });

  this->timer = salticidae::TimerEvent(pec, [this](salticidae::TimerEvent &) {
    double newTimeout = this->timeoutMul*this->timeout;
    PID oldLeader = getCurrentLeader();
    PID newLeader = getLeaderOf(this->view+1);
    if (DEBUG0) printNowTime(KLRED, "timer ran out (timeout:" + std::to_string(this->timeout) + "->" + std::to_string(newTimeout) + ") - leader=" + std::to_string(oldLeader) + "->" + std::to_string(newLeader));
    Time now = std::chrono::steady_clock::now();
    // time in seconds since the timer was last set
    double time = std::chrono::duration_cast<std::chrono::microseconds>(now - timerTime).count() / (1000 * 1000);
    if (time < this->timeout) {
      if (DEBUG1W) printNowTime(KLRED, "not yet time to timeout:" + std::to_string(time) + " < " + std::to_string(this->timeout));
      double remTime = this->timeout - time;
      this->timer.del();
      this->timer.add(remTime);
    } else {
      if (DEBUG1W) printNowTime(KLRED, "time to timeout:" + std::to_string(time) + " >= " + std::to_string(this->timeout));
      stats.incTimeouts();
      startNewViewOnTimeout();
      this->timer.del();
      this->timeout=newTimeout;
      this->timer.add(this->timeout);
      timerTime = std::chrono::steady_clock::now();
    }
  });

  HOST host = "127.0.0.1";
  PORT rport = 8760 + this->myid;
  PORT cport = 9760 + this->myid;

  NodeInfo* ownnode = nodes.find(this->myid);
  if (ownnode != NULL) {
    host  = ownnode->getHost();
    rport = ownnode->getRPort();
    cport = ownnode->getCPort();
  } else {
    std::cout << KLRED << nfo() << "couldn't find own information among nodes" << KNRM << std::endl;
  }

  //net(this->ec,config);
  salticidae::NetAddr paddr = salticidae::NetAddr(host + ":" + std::to_string(rport));
  this->pnet.start();
  this->pnet.listen(paddr);

  salticidae::NetAddr caddr = salticidae::NetAddr(host + ":" + std::to_string(cport));
  this->cnet.start();
  this->cnet.listen(caddr);

  if (DEBUG1) { std::cout << KBLU << nfo() << "connecting..." << KNRM << std::endl; }
  for (size_t j = 0; j < this->total; j++) {
    if (this->myid != j) {
      NodeInfo* othernode = nodes.find(j);
      if (othernode != NULL) {
        salticidae::NetAddr peer_addr(othernode->getHost() + ":" + std::to_string(othernode->getRPort()));
        salticidae::PeerId other{peer_addr};
        this->pnet.add_peer(other);
        this->pnet.set_peer_addr(other, peer_addr);
        this->pnet.conn_peer(other);
        if (DEBUG1) { std::cout << KBLU << nfo() << "added peer:" << j << KNRM << std::endl; }
        this->peers.push_back(std::make_pair(j,other));
      } else {
        std::cout << KLRED << nfo() << "couldn't find " << j << "'s information among nodes" << KNRM << std::endl;
      }
    }
  }
  this->pnet.reg_handler(salticidae::generic_bind(&Handler::handle_newviewRB,      this, _1, _2));
  this->pnet.reg_handler(salticidae::generic_bind(&Handler::handle_ldrprepareRB,   this, _1, _2));
  this->pnet.reg_handler(salticidae::generic_bind(&Handler::handle_bckprepareRB,   this, _1, _2));
  this->pnet.reg_handler(salticidae::generic_bind(&Handler::handle_ldrprecommitRB, this, _1, _2));
  this->pnet.reg_handler(salticidae::generic_bind(&Handler::handle_bckprecommitRB, this, _1, _2));
  this->pnet.reg_handler(salticidae::generic_bind(&Handler::handle_decideRB,       this, _1, _2));
  this->pnet.reg_handler(salticidae::generic_bind(&Handler::handle_join,           this, _1, _2));
  this->pnet.reg_handler(salticidae::generic_bind(&Handler::handle_sync,           this, _1, _2));
  this->pnet.reg_handler(salticidae::generic_bind(&Handler::handle_sync_tc,        this, _1, _2));
  this->pnet.reg_handler(salticidae::generic_bind(&Handler::handle_sync_vote,      this, _1, _2));
  this->pnet.reg_handler(salticidae::generic_bind(&Handler::handle_sync_vote_qc,   this, _1, _2));

  this->cnet.reg_handler(salticidae::generic_bind(&Handler::handle_transaction, this, _1, _2));
  this->cnet.reg_handler(salticidae::generic_bind(&Handler::handle_start, this, _1, _2));
  //this->cnet.reg_handler(salticidae::generic_bind(&Handler::handle_stop, this, _1, _2));

  // If we lose the connection with a client, we remove it from our list of clients,
  // and once there are no clients left we stop cec
/*  this->cnet.reg_conn_handler([this](const salticidae::ConnPool::conn_t &conn, bool connected) {
                                if (!connected) {
                                  salticidae::NetAddr addr = conn->get_addr();
                                  if (DEBUG0) { std::cout << KMAG << nfo() << "lost client connection?" << (std::string)addr << KNRM << std::endl; }
                                  bool connections = false;
                                  for (Clients::iterator it = this->clients.begin(); it != this->clients.end(); ++it) {
                                    CID cid = it->first;
                                    ClientNfo cnfo = (ClientNfo)(it->second);
                                    ClientNet::conn_t cconn = std::get<2>(cnfo);
                                    if (addr == cconn->get_addr()) {
                                      if (DEBUG0) { std::cout << KMAG << nfo() << "client=" << it->first << KNRM << std::endl; }
                                      (this->clients)[cid]=std::make_tuple(false,std::get<1>(cnfo),cconn);
                                      //checkStopClients();
                                    } else { if (std::get<0>(cnfo)) { connections=true; } }
                                  }
                                  if (!connections) {
                                    // no connections left with clients, so we can stop
                                    cec.stop();
                                    stopped=true;
                                  }
                                }
                                return true;
                              });*/
/*  this->pnet.reg_conn_handler([this](const salticidae::ConnPool::conn_t &conn, bool connected) {
                                if (!connected) {
                                  salticidae::NetAddr addr = conn->get_addr();
                                  if (DEBUG0) { std::cout << KMAG << nfo() << "lost peer connection?" << (std::string)addr << KNRM << std::endl; }
                                }
                                return true;
                              });*/
  // -- Salticidae


  //if (DEBUG0) { std::cout << KBLU << "size of signatures=" << ECDSA_size(this->priv) << KNRM << std::endl; }


  // Stats
  auto timeNow = std::chrono::system_clock::now();
  std::time_t time = std::chrono::system_clock::to_time_t(timeNow);
  struct tm y2k = {0};
  double seconds = difftime(time,mktime(&y2k));
  statsVals  = "stats/vals-"  + std::to_string(this->myid) + "-" + std::to_string(seconds);
  statsDone  = "stats/done-"  + std::to_string(this->myid) + "-" + std::to_string(seconds);
  statsStart = "stats/start-" + std::to_string(this->myid) + "-" + std::to_string(seconds);
  statsTimes = "stats/times-" + std::to_string(this->myid) + "-" + std::to_string(seconds);
  stats.setId(this->myid);


  std::ofstream fileStart(statsStart);
  fileStart.close();
  if (DEBUG1) std::cout << KBLU << nfo() << "printing 'start' file: " << statsStart << KNRM << std::endl;


  auto pshutdown = [&](int) {pec.stop();};
  salticidae::SigEvent pev_sigterm(pec, pshutdown);
  pev_sigterm.add(SIGTERM);

  auto cshutdown = [&](int) {cec.stop();};
  salticidae::SigEvent cev_sigterm(cec, cshutdown);
  cev_sigterm.add(SIGTERM);

  c_thread = std::thread([this]() { cec.dispatch(); });

  if (DEBUG0) { std::cout << KBLU << nfo() << "dispatching" << KNRM << std::endl; }
  pec.dispatch();
}


// Prints the time in seconds
void Handler::printNowTime(std::string col, std::string msg) {
  auto now = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(now - startView).count();
  double etime = (stats.getTotalViewTime(0).tot + time) / (1000*1000);
  std::cout << col << nfo() << msg << " @ " << etime << KNRM << std::endl;
}


void Handler::printClientInfo() {
  for (Clients::iterator it = this->clients.begin(); it != this->clients.end(); it++) {
    CID cid = it->first;
    ClientNfo cnfo = it->second;
    bool running = std::get<0>(cnfo);
    unsigned int received = std::get<1>(cnfo);
    unsigned int replied = std::get<2>(cnfo);
    ClientNet::conn_t conn = std::get<3>(cnfo);
    if (DEBUG0) { std::cout << KRED << nfo() << "CLIENT[id=" << cid << ",running=" << running << ",#received=" << received << ",#replied=" << replied << "]" << KNRM << std::endl; }
  }
}

/*void Handler::sendData(unsigned int size, char *data, std::set<PID> recipients) {
  if (DEBUG) { std::cout << KBLU << nfo() << "sending message to " << recipients.size() << " nodes" << KNRM << std::endl; }

  for (std::set<PID>::iterator it = recipients.begin(); it != recipients.end(); ++it) {
    int dst = *it;
    int valsent = this->nodes.sendTo(NODE_KIND_REPLICA,this->myid,dst,data,size);
    if (DEBUG) { std::cout << KBLU << nfo() << "message sent (" << valsent << " characters sent out of " << size
                           << "=" << sizeof(HEADER) << "+" << sizeof(RData) << "+" << sizeof(Signs)
                           << ")" << KNRM << std::endl; }
  }
}*/


std::string recipients2string(Peers recipients) {
  std::string s;
  for (Peers::iterator it = recipients.begin(); it != recipients.end(); ++it) {
    Peer peer = *it;
    s += std::to_string(std::get<0>(peer)) + ";";
  }
  return s;
}


// Keep all the ids between id1 and id2 (inclusive)
Peers Handler::from_to_peers(PID id1, PID id2) {
  Peers ret;
  for (Peers::iterator it = this->peers.begin(); it != this->peers.end(); ++it) {
    Peer peer = *it;
    PID id = std::get<0>(peer);
    bool b = false;
    if (id1 <= id2) { b = (id1 <= id && id <= id2); }
    else { b = (id1 <= id || id <= id2); }
    if (b) { ret.push_back(peer); }
  }
  return ret;
}


Peers Handler::remove_from_peers(PID id) {
  Peers ret;
  for (Peers::iterator it = this->peers.begin(); it != this->peers.end(); ++it) {
    Peer peer = *it;
    if (id != std::get<0>(peer)) { ret.push_back(peer); }
  }
  return ret;
}

Peers Handler::keep_from_peers(PID id) {
  Peers ret;
  for (Peers::iterator it = this->peers.begin(); it != this->peers.end(); ++it) {
    Peer peer = *it;
    if (id == std::get<0>(peer)) { ret.push_back(peer); }
  }
  return ret;
}


std::vector<salticidae::PeerId> getPeerids(Peers recipients) {
  std::vector<salticidae::PeerId> ret;
  for (Peers::iterator it = recipients.begin(); it != recipients.end(); ++it) {
    Peer peer = *it;
    ret.push_back(std::get<1>(peer));
  }
  return ret;
}


void Handler::sendMsgNewView(MsgNewView msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
}

void Handler::sendMsgPrepare(MsgPrepare msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgPrepare");
}

void Handler::sendMsgLdrPrepare(MsgLdrPrepare msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending(" << sizeof(msg) << "-" << sizeof(MsgLdrPrepare) << "):" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgLdrPrepare");
}

void Handler::sendMsgPreCommit(MsgPreCommit msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgPreCommit");
}

void Handler::sendMsgCommit(MsgCommit msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgCommit");
}


/*void Handler::sendMsgReply(MsgReply msg, ClientNet::conn_t recipient) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "-> clients" << KNRM << std::endl;
  this->cnet.send_msg(msg,recipient);
}*/




void Handler::sendMsgNewViewComb(MsgNewViewComb msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
}

void Handler::sendMsgLdrPrepareComb(MsgLdrPrepareComb msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgLdrPrepareComb");
}

void Handler::sendMsgPrepareComb(MsgPrepareComb msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgPrepareComb");
}

void Handler::sendMsgPreCommitComb(MsgPreCommitComb msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgPreCommitComb");
}

void Handler::sendMsgNewViewOP(MsgNewViewOPA msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
}

void Handler::sendMsgNewViewOP(MsgNewViewOPB msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
}

void Handler::sendMsgNewViewOP(MsgNewViewOPBB msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
}

void Handler::sendMsgLdrPrepareOPA(MsgLdrPrepareOPA msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgLdrPrepareOPA");
}

void Handler::sendMsgLdrPrepareOPC(MsgLdrPrepareOPC msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgLdrPrepareOPC");
}

void Handler::sendMsgLdrPrepareOPB(MsgLdrPrepareOPB msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgLdrPrepareOPB");
}

void Handler::sendMsgPreCommitOP(MsgPreCommitOP msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgPreCommitOP");
}

void Handler::sendMsgBckPrepareOP(MsgBckPrepareOP msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgBckPrepareOP");
}

void Handler::sendMsgLdrAddOP(MsgLdrAddOP msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgLdrAddOP");
}

void Handler::sendMsgBckAddOP(MsgBckAddOP msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgBckAddOP");
}




void Handler::sendMsgNewViewCh(MsgNewViewCh msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
}

void Handler::sendMsgPrepareCh(MsgPrepareCh msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgPrepareCh");
}

void Handler::sendMsgLdrPrepareCh(MsgLdrPrepareCh msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending(" << sizeof(msg) << "-" << sizeof(MsgLdrPrepareCh) << "):" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgLdrPrepareCh");
}

void Handler::sendMsgJoin(MsgJoin msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgJoin");
}

void Handler::sendMsgSync(MsgSync msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgSync");
}

void Handler::sendMsgSyncTC(MsgSyncTC msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgSyncTC");
}

void Handler::sendMsgSyncVote(MsgSyncVote msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgSyncVote");
}

void Handler::sendMsgSyncVoteQc(MsgSyncVoteQc msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgSyncVoteQc");
}

void Handler::sendMsgPmSync(MsgPmSync msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgPmSync");
}

void Handler::sendMsgPmSyncTC(MsgPmSyncTC msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgPmSyncTC");
}

void Handler::sendMsgPmSyncVote(MsgPmSyncVote msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgPmSyncVote");
}

void Handler::sendMsgPmSyncVoteQc(MsgPmSyncVoteQc msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgPmSyncVoteQc");
}

void Handler::sendMsgLdrPrepareRB(MsgLdrPrepareRB msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgLdrPrepareRB");
}

void Handler::sendMsgBckPrepareRB(MsgBckPrepareRB msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgBckPrepareRB");
}

void Handler::sendMsgLdrPreCommitRB(MsgLdrPreCommitRB msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgLdrPreCommitRB");
}

void Handler::sendMsgBckPreCommitRB(MsgBckPreCommitRB msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgBckPreCommitRB");
}

void Handler::sendMsgDecideRB(MsgDecideRB msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgDecideRB");
}

void Handler::sendMsgNewViewRB(MsgNewViewRB msg, Peers recipients) {
  if (DEBUG1) std::cout << KBLU << nfo() << "sending:" << msg.prettyPrint() << "->" << recipients2string(recipients) << KNRM << std::endl;
  this->pnet.multicast_msg(msg, getPeerids(recipients));
  if (DEBUGT) printNowTime(KBLU, "sending MsgNewViewRB");
}


Just Handler::callTEEsign() {
  auto start = std::chrono::steady_clock::now();
#if defined(BASIC_ROLL)
  just_t jout;
  sgx_status_t ret;
  sgx_status_t status = TEEsign(global_eid, &ret, &jout);
  Just just = getJust(&jout);
#else
  Just just = tf.TEEsign(stats);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEsign(time);
  stats.addTEEtime(time);
  return just;
}


Just Handler::callTEEprepare(Hash h, Just j) {
  auto start = std::chrono::steady_clock::now();
#if defined(BASIC_ROLL)
  just_t jout;
  just_t jin;
  setJust(j,&jin);
  hash_t hin;
  setHash(h,&hin);
  sgx_status_t ret;
  sgx_status_t status = TEEprepare(global_eid, &ret, &hin, &jin, &jout);
  Just just = getJust(&jout);
#else
  Just just = tf.TEEprepare(stats,this->nodes,h,j);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEprepare(time);
  stats.addTEEtime(time);
  return just;
}


Just Handler::callTEEstore(Just j) {
  auto start = std::chrono::steady_clock::now();
#if defined(BASIC_ROLL)
  just_t jout;
  just_t jin;
  setJust(j,&jin);
  sgx_status_t ret;
  sgx_status_t status = TEEstore(global_eid, &ret, &jin, &jout);
  Just just = getJust(&jout);
#else
  Just just = tf.TEEstore(stats,this->nodes,j);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEstore(time);
  stats.addTEEtime(time);
  return just;
}


Accum Handler::callTEEaccumComb(Just justs[MAX_NUM_SIGNATURES]) {
  auto start = std::chrono::steady_clock::now();
#if defined(BASIC_ROLL)
  accum_t aout;
  onejusts_t jin;
  setOneJusts(justs,&jin);
  sgx_status_t ret;
  sgx_status_t status = COMB_TEEaccum(global_eid, &ret, &jin, &aout);
  Accum acc = getAccum(&aout);
#else
  Accum acc = tc.TEEaccum(stats,this->nodes,justs);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEaccum(time);
  stats.addTEEtime(time);
  return acc;
}

// a simpler version of callTEEaccum for when all votes are for the same payload
Accum Handler::callTEEaccumCombSp(just_t just) {
  auto start = std::chrono::steady_clock::now();
#if defined(BASIC_ROLL)
  accum_t aout;
  sgx_status_t ret;
  sgx_status_t status = COMB_TEEaccumSp(global_eid, &ret, &just, &aout);
  Accum acc = getAccum(&aout);
#else
  Accum acc = tc.TEEaccumSp(stats,this->nodes,just);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEaccum(time);
  stats.addTEEtime(time);
  return acc;
}

Just Handler::callTEEsignComb() {
  auto start = std::chrono::steady_clock::now();
#if defined(BASIC_ROLL)
  just_t jout;
  sgx_status_t ret;
  sgx_status_t status = COMB_TEEsign(global_eid, &ret, &jout);
  Just just = getJust(&jout);
#else
  Just just = tc.TEEsign();
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEsign(time);
  stats.addTEEtime(time);
  return just;
}

Just Handler::callTEEprepareComb(Hash h, Accum acc) {
  auto start = std::chrono::steady_clock::now();
#if defined(BASIC_ROLL)
  just_t jout;
  accum_t ain;
  setAccum(acc,&ain);
  hash_t hin;
  setHash(h,&hin);
  sgx_status_t ret;
  sgx_status_t status = COMB_TEEprepare(global_eid, &ret, &hin, &ain, &jout);
  Just just = getJust(&jout);
#else
  Just just = tc.TEEprepare(stats,this->nodes,h,acc);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEprepare(time);
  stats.addTEEtime(time);
  return just;
}

Just Handler::callTEEstoreComb(Just j) {
  auto start = std::chrono::steady_clock::now();
#if defined(BASIC_ROLL)
  just_t jout;
  just_t jin;
  setJust(j,&jin);
  sgx_status_t ret;
  sgx_status_t status = COMB_TEEstore(global_eid, &ret, &jin, &jout);
  Just just = getJust(&jout);
#else
  Just just = tc.TEEstore(stats,this->nodes,j);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEstore(time);
  stats.addTEEtime(time);
  return just;
}


std::string h2s(hash_t hash) {
  std::string text;
  for (int i = 0; i < SHA256_DIGEST_LENGTH; i++) { text += hash.hash[i]; }
  text += std::to_string(hash.set);
  return text;
}


std::string h2sx(hash_t hash) {
  std::string text;
  for (int i = 0; i < SHA256_DIGEST_LENGTH; i++) { text += std::to_string((int)hash.hash[i]); }
  return text;
}


/////////////////////////////////////////
// OneShot


OPproposal Handler::callTEEprepareOP(Hash h) {
  auto start = std::chrono::steady_clock::now();
#if 0
  opproposal_t pout;
  hash_t hin;
  setHash(h,&hin);
  if (DEBUG1) std::cout << KLBLU << nfo() << "preparing hash:" << h2s(hin) << KNRM << std::endl;
  if (DEBUG1) std::cout << KLBLU << nfo() << "preparing hash:" << h2sx(hin) << KNRM << std::endl;
  sgx_status_t ret;
  sgx_status_t status = OP_TEEprepare(global_eid, &ret, &hin, &pout);
  OPproposal prop = getOPproposal(&pout);
#else
  OPproposal prop;
  if (DEBUG0) std::cout << KRED << nfo() << "EXIT!(8)" << KNRM << std::endl;
  exit(0);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEprepare(time);
  stats.addTEEtime(time);
  return prop;
}


OPstore Handler::callTEEstoreOP(OPproposal prop) {
  auto start = std::chrono::steady_clock::now();
#if 0
  opstore_t sout;
  opproposal_t pin;
  setOPproposal(prop,&pin);
  sgx_status_t ret;
  sgx_status_t status = OP_TEEstore(global_eid, &ret, &pin, &sout);
  OPstore store = getOPstore(&sout);
#else
  OPstore store;
  if (DEBUG0) std::cout << KRED << nfo() << "EXIT!(9)" << KNRM << std::endl;
  exit(0);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEstore(time);
  stats.addTEEtime(time);
  return store;
}


bool Handler::callTEEverifyOP(Auths auths, std::string s) {
  auto start = std::chrono::steady_clock::now();
  bool b = false;
#if 0
  payload_t pin;
  setPayload(s,&pin);
  auths_t ain;
  setAuths(auths,&ain);
  sgx_status_t ret;
  sgx_status_t status = OP_TEEverify(global_eid, &ret, &pin, &ain, &b);
  //b = true;
#else
  // TODO
  if (DEBUG0) std::cout << KRED << nfo() << "EXIT!(10)" << KNRM << std::endl;
  exit(0);
  //b = tf.TEEverify(this->nodes,j);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEverify(time);
  stats.addTEEtime(time);
  return b;
}


OPaccum Handler::callTEEaccumOp(OPstore high, OPstore justs[MAX_NUM_SIGNATURES-1]) {
  auto start = std::chrono::steady_clock::now();
#if 0
  if (DEBUG1) std::cout << KBLU << nfo() << "(callTEEaccumOP)" << KNRM << std::endl;
  //exit(0);
  opaccum_t aout;
  opstore_t jin;
  opstores_t jsin;
  setOPstore(high,&jin);
  setOPstores(justs,&jsin);
  sgx_status_t ret;
  sgx_status_t status = OP_TEEaccum(global_eid, &ret, &jin, &jsin, &aout);
  OPaccum acc = getOPaccum(&aout);
#else
  //TODO
  if (DEBUG0) std::cout << KRED << nfo() << "EXIT!(11)" << KNRM << std::endl;
  exit(0);
  OPaccum acc; // = tc.TEEaccum(this->nodes,justs);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEaccum(time);
  stats.addTEEtime(time);
  return acc;
}

// a simpler version of callTEEaccum for when all votes are for the same payload
OPaccum Handler::callTEEaccumOpSp(OPprepare just) {
  auto start = std::chrono::steady_clock::now();
#if 0
  if (DEBUG1) std::cout << KBLU << nfo() << "callTEEaccumOpSp:" << just.prettyPrint() << KNRM << std::endl;
  //exit(0);
  opaccum_t aout;
  opprepare_t pin;
  setOPprepare(just,&pin);
  sgx_status_t ret;
  sgx_status_t status = OP_TEEaccumSp(global_eid, &ret, &pin, &aout);
  OPaccum acc = getOPaccum(&aout);
  if (acc.getSize() != this->qsize) {
    if (DEBUG1) std::cout << KLRED << nfo() << "accum is of the wrong size:" << acc.prettyPrint() << KNRM << std::endl;
  }
#else
  //TODO
  if (DEBUG0) std::cout << KRED << nfo() << "EXIT!(12)" << KNRM << std::endl;
  exit(0);
  OPaccum acc; // = tc.TEEaccumSp(this->nodes,just);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEaccum(time);
  stats.addTEEtime(time);
  return acc;
}


OPvote Handler::callTEEvoteOP(Hash h) {
  auto start = std::chrono::steady_clock::now();
#if 0
  opvote_t vout;
  hash_t hin;
  setHash(h,&hin);
  if (DEBUG1) std::cout << KLBLU << nfo() << "voting on hash:" << h2s(hin) << KNRM << std::endl;
  if (DEBUG1) std::cout << KLBLU << nfo() << "voting on hash:" << h2sx(hin) << KNRM << std::endl;
  sgx_status_t ret;
  sgx_status_t status = OP_TEEvote(global_eid, &ret, &hin, &vout);
  OPvote vote = getOPvote(&vout);
#else
  OPvote vote;
  if (DEBUG0) std::cout << KRED << nfo() << "EXIT!(13)" << KNRM << std::endl;
  exit(0);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEprepare(time);
  stats.addTEEtime(time);
  return vote;
}


/////////////////////////////////////////
// Chained HotStuff


Just Handler::callTEEsignCh() {
  auto start = std::chrono::steady_clock::now();
#if defined(BASIC_ROLL)
  just_t jout;
  sgx_status_t ret;
  sgx_status_t status = CH_TEEsign(global_eid, &ret, &jout);
  Just just = getJust(&jout);
#else
  Just just = tp.TEEsign();
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEsign(time);
  stats.addTEEtime(time);
  return just;
}


Just Handler::callTEEprepareCh(JBlock block, JBlock block0, JBlock block1) {
  auto start = std::chrono::steady_clock::now();
#if defined(BASIC_ROLL)
  just_t jout;
  // 1st block
  jblock_t jin;
  setJBlock(block,&jin);
  // 2nd block
  jblock_t jin0;
  setJBlock(block0,&jin0);
  // 3rd block
  jblock_t jin1;
  setJBlock(block1,&jin1);
  // --
  sgx_status_t ret;
  sgx_status_t status = CH_TEEprepare(global_eid, &ret, &jin, &jin0, &jin1, &jout);
  Just just = getJust(&jout);
#else
  Just just = tp.TEEprepare(stats,this->nodes,block,block0,block1);
#endif
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEprepare(time);
  stats.addTEEtime(time);
  return just;
}


/////////////////////////////////////////
// Pacemaker


Sync Handler::callTEEsync(RBstoreAuth store) {
  auto start = std::chrono::steady_clock::now();

  rbstore_auth_t p;
  setRBstoreAuth(store,&p);
  sync_t w;
  sgx_status_t ret;
  sgx_status_t status = TEEsync(global_eid, &ret, &p, &w);
  Sync sync = getSync(&w);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  //stats.addTEEaccum(time);
  //stats.addTEEtime(time);

  return sync;
}

Join Handler::callTEEjoinRequest(Session s) {
  auto start = std::chrono::steady_clock::now();

  join_t w;
  sgx_status_t ret;
  sgx_status_t status = TEEjoinRequest(global_eid, &ret, &s, &w);
  Join join = getJoin(&w);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  //stats.addTEEaccum(time);
  //stats.addTEEtime(time);

  return join;
}

SyncVoteAuth Handler::callTEEsyncVote(RBaccumSyncAuth acc, INonces nonces) {
  auto start = std::chrono::steady_clock::now();

  SyncVoteAuth jvote;

  rbaccum_sync_auth_t acct; // input
  setRBaccumSyncAuth(acc,&acct);
  sgx_status_t ret;

  if (nonces.size() > 0) {

    inonces_t noncest;       // input
    sync_vote_auth_t jv;  // output
    setINonces(nonces,&noncest);
    sgx_status_t status = TEEsyncVote(global_eid, &ret, &acct, &noncest, &jv);

    if (DEBUG1) { std::cout << KBLU << nfo() << "voted: " << jv.auth.id << KNRM << std::endl; }

    jvote = getSyncVoteAuth(&jv);

  } else {

    sp_sync_vote_auth_t jv;  // output
    sgx_status_t status = TEEspSyncVote(global_eid, &ret, &acct, &jv);

    if (DEBUG1) { std::cout << KBLU << nfo() << "voted: " << jv.auth.id << KNRM << std::endl; }

    jvote = getSpSyncVoteAuth(&jv);

  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  //stats.addTEEaccum(time);
  //stats.addTEEtime(time);

  return jvote;
}

RBstoreAuth Handler::callTEEsyncEnd(SyncVoteAuths votes) {
  auto start = std::chrono::steady_clock::now();

  rbstore_auth_t j; // output
  sgx_status_t ret;

  if (votes.getVote().getJoins().size() > 0) {

    sync_vote_auths_t qc; // input
    setSyncVoteAuths(votes,&qc);
    sgx_status_t status = TEEsyncEnd(global_eid, &ret, &qc, &j);

  } else {

    sp_sync_vote_auths_t qc; // input
    setSpSyncVoteAuths(votes,&qc);
    sgx_status_t status = TEEspSyncEnd(global_eid, &ret, &qc, &j);

  }

  RBstoreAuth store = getRBstoreAuth(&j);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  //stats.addTEEaccum(time);
  //stats.addTEEtime(time);

  return store;
}


/////////////////////////////////////////
// Pacemaker

PmSync Handler::callTEEpmSync(FVJust store) {
  auto start = std::chrono::steady_clock::now();

  fvjust_t j;
  setFVJust(store,&j);
  pm_sync_t s;
  sgx_status_t ret;
  sgx_status_t status = TEEpmSync(global_eid, &ret, &j, &s);
  PmSync sync = getPmSync(&s);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  //stats.addTEEaccum(time);
  //stats.addTEEtime(time);

  return sync;
}

PmSync Handler::callTEEpmSyncVote(PmSync sync) {
  auto start = std::chrono::steady_clock::now();

  pm_sync_t jout; // output
  pm_sync_t jin;  // input
  setPmSync(sync,&jin);
  sgx_status_t ret;
  sgx_status_t status = TEEpmSyncVote(global_eid, &ret, &jin, &jout);

  if (DEBUG1) { std::cout << KBLU << nfo() << "voted: " << jout.auth.id << KNRM << std::endl; }

  PmSync jvote = getPmSync(&jout);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  //stats.addTEEaccum(time);
  //stats.addTEEtime(time);

  return jvote;
}

FVJust Handler::callTEEpmSyncEnd(PmSyncs votes) {
  auto start = std::chrono::steady_clock::now();

  fvjust_t   jout; // output
  pm_syncs_t jin;  // input
  setPmSyncs(votes,&jin);
  sgx_status_t ret;
  sgx_status_t status = TEEpmSyncEnd(global_eid, &ret, &jin, &jout);

  FVJust just = getFVJust(&jout);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  //stats.addTEEaccum(time);
  //stats.addTEEtime(time);

  return just;
}


/////////////////////////////////////////
// Rollback-resilient Damysus


RBprepareAuth Handler::callTEEprepareRB(Hash hblock) {
  auto start = std::chrono::steady_clock::now();

  hash_t hblockin;
  rbprepare_auth_t pout;
  setHash(hblock,&hblockin);
  sgx_status_t ret;
  sgx_status_t status = TEEprepareRB(global_eid, &ret, &hblockin, &pout);
  RBprepareAuth prep = getRBprepareAuth(&pout);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEprepare(time);
  stats.addTEEtime(time);
  return prep;
}

RBstoreAuth Handler::callTEEstoreRB(RBprepareAuths j) {
  auto start = std::chrono::steady_clock::now();

  rbstore_auth_t jout;
  rbprepare_auths_t jin;
  setRBprepareAuths(j,&jin);
  sgx_status_t ret;
  sgx_status_t status = TEEstoreRB(global_eid, &ret, &jin, &jout);
  RBstoreAuth store = getRBstoreAuth(&jout);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTEEstore(time);
  stats.addTEEtime(time);
  return store;
}

RBnewviewAuth Handler::callTEEnewviewRB(RBstoreAuth store) {
  auto start = std::chrono::steady_clock::now();

  rbnewview_auth_t jout;
  rbstore_auth_t jin;
  setRBstoreAuth(store,&jin);
  sgx_status_t ret;
  sgx_status_t status = TEEnewviewRB(global_eid, &ret, &jin, &jout);
  RBnewviewAuth newview = getRBnewviewAuth(&jout);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
//  stats.addTEEstore(time);
  stats.addTEEtime(time);
  return newview;
}

RBaccumNvAuth Handler::callTEEaccumNvRB(RBnewviewAuth newview, std::set<RBnewviewAuth> newviews) {
  auto start = std::chrono::steady_clock::now();

  rbnewview_auth_t jin;
  rbnewviews_t jsin;
  rbaccum_nv_auth_t jout;
  setRBnewviewAuth(newview,&jin);
  setRBnewviews(newviews,&jsin);
  sgx_status_t ret;
  sgx_status_t status = TEEaccumNvRB(global_eid, &ret, &jin, &jsin, &jout);
  RBaccumNvAuth acc = getRBaccumNvAuth(&jout);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
//  stats.addTEEstore(time);
  stats.addTEEtime(time);
  return acc;
}

RBaccumSyncAuth Handler::callTEEaccumSyncRB(Sync sync, std::set<Sync> syncs) {
  auto start = std::chrono::steady_clock::now();

  sync_t jin;
  syncs_t jsin;
  rbaccum_sync_auth_t jout;
  setSync(sync,&jin);
  setSyncs(syncs,&jsin);
  sgx_status_t ret;
  sgx_status_t status = TEEaccumSyncRB(global_eid, &ret, &jin, &jsin, &jout);
  RBaccumSyncAuth acc = getRBaccumSyncAuth(&jout);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
//  stats.addTEEstore(time);
  stats.addTEEtime(time);
  return acc;
}


/////////////////////////////////////////
// Stuff


Sign Handler::Ssign(KEY priv, PID signer, std::string text) {
  auto start = std::chrono::steady_clock::now();
  Sign s = Sign(priv,signer,text);
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addCryptoSignTime(time);
  return s;
}


// reset the timer, and record the current view
void Handler::setTimer() {
  if (DEBUG1) printNowTime(KMAG, "deleting timer(timeout:" + std::to_string(this->timeout) + ")");
  this->timer.del();
  this->timeout = this->timeout / this->timeoutDiv;
  if (this->timeout < this->initTimeout) { this->timeout = this->initTimeout; }
  if (DEBUG1) printNowTime(KMAG, "adding timer(timeout:" + std::to_string(this->timeout) + ")");
  this->timer.add(this->timeout);
  this->timerView = this->view;
  timerTime = std::chrono::steady_clock::now();
}


void Handler::getStarted() {
  //if (DEBUG1) std::cout << KLRED << nfo() << "starting" << KNRM << std::endl;
  startTime = std::chrono::steady_clock::now();
  startView = std::chrono::steady_clock::now();
  // Send new-view to the leader of the current view

  PID leader = getCurrentLeader();
  Peers recipients = keep_from_peers(leader);

  PID nextLeader = getLeaderOf(this->view+1);
  Peers nextRecipients = keep_from_peers(nextLeader);

  if (DEBUG1) std::cout << KBLU << nfo() << "... getting started ..." << KNRM << std::endl;

  // We start the timer
  //setTimer();

  // starting a view
  //this->lastRBstore = RBstoreAuth(RBstore(),Auth());
  if (DEBUG1) std::cout << KLRED << nfo() << "initial store:" << this->lastRBstore.prettyPrint() << KNRM << std::endl;
  startNewViewOrJoinRB(this->lastRBstore);
}


/*bool Handler::verifyPrepare(Message<Proposal> msg)        { return msg.verify(this->nodes); }*/
bool Handler::verifyTransaction(MsgTransaction msg) { return true; /*msg.verify(this->nodes);*/ }
//bool Handler::verifyStart(MsgStart msg) { return true; /*msg.verify(this->nodes);*/ }


void Handler::handleEarlierMessages() {
  // *** THIS IS FOR LATE NODES TO PRO-ACTIVELY PROCESS MESSAGES THEY HAVE ALREADY RECEIVED FOR THE NEW VIEW ***
  // We now check whether we already have enough information to start the next view if we're the leader
  if (amCurrentLeader()) {
    Signs signsNV = this->log.getNewView(this->view,this->qsize);
    if (signsNV.getSize() == this->qsize) {
      // we have enough new view messages to start the new view
      prepare();
    }
  } else {
    // First we check whether the view has already been locked
    // (i.e., we received a pre-commit certificate from the leader),
    // in which case we don't need to go through the previous steps.
    Signs signsPc = (this->log).getPrecommit(this->view,this->qsize);
    if (signsPc.getSize() == this->qsize) {
      if (DEBUG1) std::cout << KMAG << nfo() << "catching up using pre-commit certificate" << KNRM << std::endl;
      Just justPc = this->log.firstPrecommit(this->view);
      // We skip the prepare phase (this is otherwise a TEEprepare):
      callTEEsign();
      // We skip the pre-commit phase (this is otherwise a TEEstore):
      callTEEsign();
      // We store the pre-commit certificate
      respondToPreCommitJust(justPc);
      Signs signsCom = (this->log).getCommit(this->view,this->qsize);
      if (signsCom.getSize() == this->qsize) {
        Just justCom = this->log.firstCommit(this->view);
        executeRData(justCom.getRData());
      }
    } else { // We don't have enough pre-commit signatures
      // TODO: we could still have enough commit signatures, in which case we might want to skip to that phase
      Signs signsPrep = (this->log).getPrepare(this->view,this->qsize);
      if (signsPrep.getSize() == this->qsize) {
        if (DEBUG1) std::cout << KMAG << nfo() << "catching up using prepare certificate" << KNRM << std::endl;
        // TODO: If we're late, we currently store two prepare messages (in the prepare phase,
        // the one from the leader with 1 sig; and in the pre-commit phase, the one with f+1 sigs.
        Just justPrep = this->log.firstPrepare(this->view);
        // We skip the prepare phase (this is otherwise a TEEprepare):
        callTEEsign();
        // We store the prepare certificate
        respondToPrepareJust(justPrep);
      } else {
        MsgLdrPrepare msgProp = this->log.firstProposal(this->view);
        if (msgProp.signs.getSize() == 1) { // If we've stored the leader's proposal
          if (DEBUG1) std::cout << KMAG << nfo() << "catching up using leader proposal" << KNRM << std::endl;
          Proposal prop = msgProp.prop;
          respondToProposal(prop.getJust(),prop.getBlock());
        }
      }
    }
  }
}


// TODO: also trigger new-views when there is a timeout
void Handler::startNewView() {
  Just just = callTEEsign();
  // generate justifications until we can generate one for the next view
  while (just.getRData().getPropv() <= this->view) { just = callTEEsign(); }
  // increment the view
  // *** THE NODE HAS NOW MOVED TO THE NEW-VIEW ***
  this->view++;

  // We start the timer
  setTimer();

  // if the lastest justification we've generated is for what is now the current view (since we just incremented it)
  // and round 0, then send a new-view message
  if (just.getRData().getPropv() == this->view && just.getRData().getPhase() == PH1_NEWVIEW) {
    MsgNewView msg(just.getRData(),just.getSigns());
    if (amCurrentLeader()) {
      handleEarlierMessages();
      handleNewview(msg);
    }
    else {
      PID leader = getCurrentLeader();
      Peers recipients = keep_from_peers(leader);
      sendMsgNewView(msg,recipients);
      handleEarlierMessages();
    }
  } else {
    // Something wrong happened
  }
}


void Handler::recordStats() {
  if (DEBUG1) std::cout << KLGRN << nfo() << "DONE - printing stats" << KNRM << std::endl;

  unsigned int quant1 = this->quant1;
  unsigned int quant2 = this->quant2; //10;

  if (DEBUG1Y) { stats.printAllTimes(); }

  // Throughput
  //auto endTime = std::chrono::steady_clock::now();
  //double time = std::chrono::duration_cast<std::chrono::microseconds>(endTime - startTime).count();
  Times totv = stats.getTotalViewTime(quant2);
  double kopsv = ((totv.n)*(MAX_NUM_TRANSACTIONS)*1.0) / 1000;
  double secsView = /*time*/ totv.tot / (1000*1000);
  if (DEBUG0) std::cout << KBLU << nfo() << "VIEW|view=" << this->view << ";Kops=" << kopsv << ";secs=" << secsView << ";n=" << totv.n << KNRM << std::endl;
  double throughputView = kopsv/secsView;

  // Debugging - handle
  Times toth = stats.getTotalHandleTime(quant1);
  double kopsh = ((toth.n)*(MAX_NUM_TRANSACTIONS)*1.0) / 1000;
  double secsHandle = /*time*/ toth.tot / (1000*1000);
  if (DEBUG0) std::cout << KBLU << nfo() << "HANDLE|view=" << this->view << ";Kops=" << kopsh << ";secs=" << secsHandle << ";n=" << toth.n << KNRM << std::endl;
  //double throughputHandle = kopsh/secsHandle;
  //std::ofstream fileThroughputHandle(statsThroughputHandle);
  //fileThroughputHandle << std::to_string(throughputHandle);
  //fileThroughputHandle.close();

  // Latency
  double latencyView = (totv.tot/totv.n / 1000)/* milli-seconds spent on views */;

  // Handle
  double handle = (toth.tot / 1000); /* milli-seconds spent on handling messages */

  // Timeouts
  unsigned int timeouts = stats.getTimeouts();

  // onepbs
  unsigned int onepbs = stats.getNumOnePBs();

  // onepcs
  unsigned int onepcs = stats.getNumOnePCs();

  // Crypto
  double ctimeS  = stats.getCryptoSignTime();
  double cryptoS = (ctimeS / 1000); /* milli-seconds spent on crypto */
  double ctimeV  = stats.getCryptoVerifTime();
  double cryptoV = (ctimeV / 1000); /* milli-seconds spent on crypto */

  if (this->myid < this->numJoiners) {
    if (DEBUG1) std::cout << KLBLU << nfo() << "not printing stats because joiners" << KNRM << std::endl;
  } else {
    if (DEBUG1) std::cout << KLBLU << nfo() << "print stats because not joiners" << KNRM << std::endl;
    std::ofstream fileVals(statsVals);
    fileVals << std::to_string(throughputView)
             << " " << std::to_string(latencyView)
             << " " << std::to_string(handle)
             << " " << std::to_string(timeouts)
             << " " << std::to_string(onepbs)
             << " " << std::to_string(onepcs)
             << " " << std::to_string(stats.getCryptoSignNum())
             << " " << std::to_string(cryptoS)
             << " " << std::to_string(stats.getCryptoVerifNum())
             << " " << std::to_string(cryptoV);
    fileVals.close();

    // FOR DEBUGGING PURPOSES: print all the times (for each view)
    std::ofstream fileDebug(statsTimes);
    std::vector<double> vtimes = stats.getViewTimes();
    for (std::vector<double>::iterator it = vtimes.begin(); it != vtimes.end(); it++) {
      fileDebug << " " << std::to_string((double)*it);
    }
    fileDebug.close();

  }

  // Done
  std::ofstream fileDone(statsDone);
  fileDone.close();
  if (DEBUG1) std::cout << KBLU << nfo() << "printing 'done' file: " << statsDone << KNRM << std::endl;

  if (hardStop) {
    // stopping client ec
    if (DEBUG1) std::cout << KBLU << nfo() << "stopping ec..." << KNRM << std::endl;
    this->req_tcall->async_call([this](salticidae::ThreadCall::Handle &) { cec.stop(); });
    if (DEBUG1) std::cout << KBLU << nfo() << "joining..." << KNRM << std::endl;
    c_thread.join();
    if (DEBUG1) std::cout << KBLU << nfo() << "joined" << KNRM << std::endl;

    // stopping peer ec
    pec.stop();
    if (DEBUG1) std::cout << KBLU << nfo() << "stopped" << KNRM << std::endl;
    //raise(SIGTERM);
  }
}


// send replies corresponding to 'hash'
void Handler::replyTransactions(Transaction *transactions) {
  for (int i = 0; i < MAX_NUM_TRANSACTIONS; i++) {
    Transaction trans = transactions[i];
    CID cid = trans.getCid();
    TID tid = trans.getTid();
    // The transaction id '0' is reserved for dummy transactions
    if (tid != 0) {
      Clients::iterator cit = this->clients.find(cid);
      if (cit != this->clients.end()) {
        rep_queue.enqueue(std::make_pair(tid,cid));
        //MsgReply reply(tid);
        //ClientNet::conn_t recipient = std::get<2>(cit->second);
        if (DEBUG1) std::cout << KBLU << nfo() << "sending reply to " << cid << ":" << tid << KNRM << std::endl;
        //sendMsgReply(reply,recipient);
      } else {
        if (DEBUG0) { std::cout << KBLU << nfo() << "unknown client: " << cid << KNRM << std::endl; }
      }
    }
  }
}


// send replies corresponding to 'hash'
void Handler::replyHash(Hash hash) {
  std::map<View,Block>::iterator it = this->blocks.find(this->view);
  if (it != this->blocks.end()) {
    Block block = (Block)it->second;
    if (block.hash() == hash) {
      if (DEBUG1) std::cout << KBLU << nfo() << "found block for view=" << this->view << ":" << block.prettyPrint() << KNRM << std::endl;
      replyTransactions(block.getTransactions());
    } else {
      if (DEBUG1) std::cout << KBLU << nfo() << "recorded block but incorrect hash for view " << this->view << KNRM << std::endl;
      if (DEBUG1) std::cout << KBLU << nfo() << "checking hash:" << hash.toString() << KNRM << std::endl;
    }
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "no block recorded for view " << this->view << KNRM << std::endl;
  }
}


bool Handler::timeToStop() {
  //bool b = this->maxViews > 0 && this->maxViews <= this->viewsWithoutNewTrans;
  bool b = this->maxViews > 0 && this->maxViews <= this->view+1;
  if (DEBUG) { std::cout << KBLU << nfo() << "timeToStop=" << b << ";maxViews=" << this->maxViews << ";viewsWithoutNewTrans=" << this->viewsWithoutNewTrans << ";pending-transactions=" << this->transactions.size() << KNRM << std::endl; }
  if (DEBUG1) { if (b) { std::cout << KBLU << nfo() << "maxViews=" << this->maxViews << ";viewsWithoutNewTrans=" << this->viewsWithoutNewTrans << ";pending-transactions=" << this->transactions.size() << KNRM << std::endl; } }
  return b;
}


void Handler::executeRData(RData rdata) {
  auto endView = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(endView - startView).count();
  startView = endView;
  stats.incExecViews();
  stats.addTotalViewTime(time);
  if (this->transactions.empty()) { this->viewsWithoutNewTrans++; } else { this->viewsWithoutNewTrans = 0; }

  // Execute
  // TODO: We should wait until we received the block corresponding to the hash to execute
  if (DEBUG0 && DEBUGE) std::cout << KRED << nfo() << "R-EXECUTE(" << this->view << "/" << this->maxViews << ":" << time << ")" << stats.toString() << KNRM << std::endl;
  //if (this->view%100 == 0) { std::cout << KRED << nfo() << "R-EXECUTE(" << this->view << "/" << this->maxViews << ":" << time << ")" << stats.toString() << KNRM << std::endl; }
  //if (this->view%100 == 0) { printClientInfo(); }
  replyHash(rdata.getProph());

  if (timeToStop()) {
    recordStats();
  } else {
    startNewView();
  }
}


// For leaders to generate a commit with f+1 signatures
void Handler::initiateCommit(RData rdata) {
  Signs signs = (this->log).getCommit(rdata.getPropv(),this->qsize);
  // We should not need to check the size of 'signs' as this function should only be called, when this is possible
  if (signs.getSize() == this->qsize) {
    MsgCommit msgCom(rdata,signs);
    Peers recipients = remove_from_peers(this->myid);
    sendMsgCommit(msgCom,recipients);
    if (DEBUG) std::cout << KBLU << nfo() << "sent commit certificate to backups (" << msgCom.prettyPrint() << ")" << KNRM << std::endl;

    // We can now execute the block:
    executeRData(rdata);
  }
}


// For leaders to generate a pre-commit with f+1 signatures
void Handler::initiatePrecommit(RData rdata) {
  Signs signs = (this->log).getPrecommit(rdata.getPropv(),this->qsize);
  // We should not need to check the size of 'signs' as this function should only be called, when this is possible
  if (signs.getSize() == this->qsize) {
    MsgPreCommit msgPc(rdata,signs);
    Peers recipients = remove_from_peers(this->myid);
    sendMsgPreCommit(msgPc,recipients);
    if (DEBUG) std::cout << KBLU << nfo() << "sent pre-commit to backups (" << msgPc.prettyPrint() << ")" << KNRM << std::endl;

    // The leader also stores the prepare message
    Just justCom = callTEEstore(Just(rdata,signs));
    MsgCommit msgCom(justCom.getRData(),justCom.getSigns());

    // We store our own commit in the log
    if (this->qsize <= this->log.storeCom(msgCom)) {
      initiateCommit(justCom.getRData());
    }
  }
}


// For leaders to forward prepare justifications to all nodes
void Handler::initiatePrepare(RData rdata) {
  Signs signs = (this->log).getPrepare(rdata.getPropv(),this->qsize);
  if (DEBUG) std::cout << KBLU << nfo() << "prepare signatures: " << signs.prettyPrint() << KNRM << std::endl;
  // We should not need to check the size of 'signs' as this function should only be called, when this is possible
  if (signs.getSize() == this->qsize) {
    MsgPrepare msgPrep(rdata,signs);
    Peers recipients = remove_from_peers(this->myid);
    sendMsgPrepare(msgPrep,recipients);
    if (DEBUG) std::cout << KBLU << nfo() << "sent prepare certificate to backups (" << msgPrep.prettyPrint() << ")" << KNRM << std::endl;

    // The leader also stores the prepare message
    Just justPc = callTEEstore(Just(rdata,signs));
    MsgPreCommit msgPc(justPc.getRData(),justPc.getSigns());

    // We store our own pre-commit in the log
    if (this->qsize <= this->log.storePc(msgPc)) {
      initiatePrecommit(justPc.getRData());
    }
  }
}


Block Handler::createNewBlock(Hash hash) {
  std::lock_guard<std::mutex> guard(mu_trans);

  if (DEBUG1) std::cout << KBLU << nfo() << "in createNewBlock" << KNRM << std::endl;

  auto start = std::chrono::steady_clock::now();

  Transaction trans[MAX_NUM_TRANSACTIONS];
  int i = 0;

  // We fill the block we have with transactions we have received so far
  while (i < MAX_NUM_TRANSACTIONS && !this->transactions.empty()) {
    trans[i]=this->transactions.front();
    this->transactions.pop_front();
    i++;
  }

  // std::ofstream d("debug", std::ios_base::app);
  // d << std::to_string(i) << "\n";
  // d.close();

  if (DEBUG1) { std::cout << KGRN << nfo() << "filled block with " << i << " transactions" << KNRM << std::endl; }

  unsigned int size = i;
  // we fill the rest with dummy transactions
  while (i < MAX_NUM_TRANSACTIONS) {
    trans[i]=Transaction();
    i++;
  }
  //size = i;
  unsigned int id = std::stoi(std::to_string(this->myid) + std::to_string(this->view));
  Block b(id,hash,size,trans);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalNewTime(time);

  return b;
}


// For leader to do begin a view (prepare phase)
void Handler::prepare() {
  auto start = std::chrono::steady_clock::now();
  // We first create a block that extends the highest prepared block
  Just justNV = this->log.findHighestNv(this->view);

  Block block = createNewBlock(justNV.getRData().getJusth());
  //transactions.clear();

  // We create our own justification for that block
  Just justPrep = callTEEprepare(block.hash(),justNV);
  if (justPrep.isSet()) {
    if (DEBUG1) std::cout << KBLU << nfo() << "storing block for view=" << this->view << ":" << block.prettyPrint() << KNRM << std::endl;
    this->blocks[this->view]=block;

    // We create a message out of that commitment, which we'll store in our log
    Signs signs = justPrep.getSigns();
    MsgPrepare msgPrep(justPrep.getRData(),signs);

    // We now create a proposal out of that block to send out to the other replicas
    Proposal prop(justNV,block);

    //if (DEBUG) std::cout << KBLU << nfo() << "prepare signature (" << signs.prettyPrint() << ")" << KNRM << std::endl;

    // We send this proposal in a prepare message
    MsgLdrPrepare msgProp(prop,signs);
    Peers recipients = remove_from_peers(this->myid);
    sendMsgLdrPrepare(msgProp,recipients);
    if (DEBUG) std::cout << KBLU << nfo() << "sent prepare (" << msgProp.prettyPrint() << ") to backups" << KNRM << std::endl;

    // We store our own proposal in the log
    if (this->qsize <= this->log.storePrep(msgPrep)) {
      initiatePrepare(justPrep.getRData());
    }
  } else {
    if (DEBUG2) std::cout << KBLU << nfo() << "bad justification" << justPrep.prettyPrint() << KNRM << std::endl;
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalLPrepTime(time);
}


// NEW-VIEW messages are received by leaders
// Once a leader has received f+1 new-view messages, it creates a proposal out of the highest prepared block
// and sends this proposal in a PREPARE message
void Handler::handleNewview(MsgNewView msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  Hash   hashP = msg.rdata.getProph();
  View   viewP = msg.rdata.getPropv();
  Phase1 ph    = msg.rdata.getPhase();
  if (hashP.isDummy() && viewP >= this->view && ph == PH1_NEWVIEW && amLeaderOf(viewP)) {
    if (this->log.storeNv(msg) == this->qsize && viewP == this->view) {
      prepare();
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded:" << msg.prettyPrint() << KNRM << std::endl;
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalNvTime(time);
}

void Handler::respondToProposal(Just justNv, Block block) {
  // We create our own justification for that block
  Just newJustPrep = callTEEprepare(block.hash(),justNv);
  if (newJustPrep.isSet()) {
    if (DEBUG1) std::cout << KBLU << nfo() << "storing block for view=" << this->view << ":" << block.prettyPrint() << KNRM << std::endl;
    this->blocks[this->view]=block;
    // We create a message out of that commitment, which we'll store in our log
    MsgPrepare msgPrep(newJustPrep.getRData(),newJustPrep.getSigns());
    Peers recipients = keep_from_peers(getCurrentLeader());
    sendMsgPrepare(msgPrep,recipients);
  } else {
    if (DEBUG2) std::cout << KBLU << nfo() << "bad justification" << newJustPrep.prettyPrint() << KNRM << std::endl;
  }
}


bool Handler::Sverify(Signs signs, PID id, Nodes nodes, std::string s) {
  //std::cout << KBLU << nfo() << "verifying:" << signs.getSize() << KNRM << std::endl;
  //std::cout << KBLU << nfo() << "stats-1:" << stats.getCryptoVerifNum() << KNRM << std::endl;
  bool b = signs.verify(stats, id, nodes, s);
  //std::cout << KBLU << nfo() << "stats-2:" << stats.getCryptoVerifNum() << KNRM << std::endl;
  return b;
}


bool Handler::verifyJust(Just just) {
  return Sverify(just.getSigns(),this->myid,this->nodes,just.getRData().toString());
}


// This is only for backups
void Handler::handleLdrPrepare(MsgLdrPrepare msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  Proposal prop = msg.prop;
  Just justNV = prop.getJust();
  RData rdataNV = justNV.getRData();
  Block b = prop.getBlock();

  // We re-construct the justification generated by the leader
  RData rdataLdrPrep(b.hash(),rdataNV.getPropv(),rdataNV.getJusth(),rdataNV.getJustv(),PH1_PREPARE);
  Just ldrJustPrep(rdataLdrPrep,msg.signs);
  bool vm = verifyJust(ldrJustPrep);

  if (rdataNV.getPropv() >= this->view
      && vm
      && b.extends(rdataNV.getJusth())) {
    // If the message is for the current view we act upon it right away
    if (rdataNV.getPropv() == this->view) {
      respondToProposal(justNV,b);
    } else{
      // If the message is for later, we store it
      if (DEBUG1) std::cout << KMAG << nfo() << "storing:" << msg.prettyPrint() << KNRM << std::endl;
      this->log.storeProp(msg);
    }
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  //if (DEBUGT) std::cout << KMAG << nfo() << "MsgLdrPrepare3:" << time << KNRM << std::endl;
}


// For backups to respond to prepare certificates received from the leader
void Handler::respondToPrepareJust(Just justPrep) {
  Just justPc = callTEEstore(justPrep);
  MsgPreCommit msgPc(justPc.getRData(),justPc.getSigns());
  Peers recipients = keep_from_peers(getCurrentLeader());
  sendMsgPreCommit(msgPc,recipients);
  if (DEBUG) std::cout << KBLU << nfo() << "sent pre-commit (" << msgPc.prettyPrint() << ") to leader" << KNRM << std::endl;
}


// This is for both for the leader and backups
void Handler::handlePrepare(MsgPrepare msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  RData rdata = msg.rdata;
  Signs signs = msg.signs;
  if (rdata.getPropv() == this->view) {
    if (amCurrentLeader()) {
      // As a leader, we wait for f+1 proposals before we calling TEEpropose
      if (this->log.storePrep(msg) == this->qsize) {
        initiatePrepare(rdata);
      }
    } else {
      // As a replica, if we receive a prepare message with f+1 signatures, then we pre-commit
      if (signs.getSize() == this->qsize) {
        respondToPrepareJust(Just(rdata,signs));
      }
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "storing:" << msg.prettyPrint() << KNRM << std::endl;
    if (rdata.getPropv() > this->view) { this->log.storePrep(msg); }
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}


// For backups to respond to pre-commit certificates received from the leader
void Handler::respondToPreCommitJust(Just justPc) {
  Just justCom = callTEEstore(justPc);
  MsgCommit msgCom(justCom.getRData(),justCom.getSigns());
  Peers recipients = keep_from_peers(getCurrentLeader());
  sendMsgCommit(msgCom,recipients);
  if (DEBUG) std::cout << KBLU << nfo() << "sent commit (" << msgCom.prettyPrint() << ") to leader" << KNRM << std::endl;
}


void Handler::handlePrecommit(MsgPreCommit msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  RData  rdata = msg.rdata;
  Signs  signs = msg.signs;
  View   propv = rdata.getPropv();
  Phase1 phase = rdata.getPhase();
  if (propv == this->view && phase == PH1_PRECOMMIT) {
    if (amCurrentLeader()) {
      // As a leader, we wait for f+1 pre-commits before we combine the messages
      if (this->log.storePc(msg) == this->qsize) {
        // as a learder bundle the pre-commits together and send them to the backups
        initiatePrecommit(rdata);
      }
    } else {
      // As a backup:
      if (signs.getSize() == this->qsize) {
        respondToPreCommitJust(Just(rdata,signs));
      }
    }
  } else {
    if (rdata.getPropv() > this->view) {
      if (DEBUG1) std::cout << KMAG << nfo() << "storing:" << msg.prettyPrint() << KNRM << std::endl;
      this->log.storePc(msg);
      // TODO: we'll have to check whether we have this information later
    }
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}


void Handler::handleCommit(MsgCommit msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  RData  rdata = msg.rdata;
  Signs  signs = msg.signs;
  View   propv = rdata.getPropv();
  Phase1 phase = rdata.getPhase();
  if (propv == this->view && phase == PH1_COMMIT) {
    if (amCurrentLeader()) {
      // As a leader, we wait for f+1 commits before we combine the messages
      if (this->log.storeCom(msg) == this->qsize) {
        initiateCommit(rdata);
      }
    } else {
      // As a backup:
      if (signs.getSize() == this->qsize && verifyJust(Just(rdata,signs))) {
        executeRData(rdata);
      }
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded:" << msg.prettyPrint() << KNRM << std::endl;
    if (propv > this->view) {
      if (amLeaderOf(propv)) {
        // If we're the leader of that later view, we log the message
        // We don't need to verify it as the verification will be done inside the TEE
        this->log.storeCom(msg);
      } else {
        // If we're not the leader, we only store it, if we can verify it
        if (verifyJust(Just(rdata,signs))) { this->log.storeCom(msg); }
      }
      // TODO: we'll have to check whether we have this information later
    }
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}


void Handler::handleTransaction(MsgTransaction msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  if (verifyTransaction(msg)) {
    Transaction trans = msg.trans;
    CID cid = trans.getCid();
    Clients::iterator it = this->clients.find(cid);
    if (it != this->clients.end()) { // we found an entry for 'cid'
      ClientNfo cnfo = (ClientNfo)(it->second);
      bool running = std::get<0>(cnfo);
      if (running) {
        // We got a new transaction from a live client
        //this->viewsWithoutNewTrans=0;
        if ((this->transactions).size() < (this->transactions).max_size()) {
          if (DEBUG1) { std::cout << KBLU << nfo() << "pushing transaction:" << trans.prettyPrint() << KNRM << std::endl; }
          (this->clients)[cid]=std::make_tuple(true,std::get<1>(cnfo)+1,std::get<2>(cnfo),std::get<3>(cnfo));
          this->transactions.push_back(trans);
        } else { if (DEBUG0) { std::cout << KMAG << nfo() << "too many transactions (" << (this->transactions).size() << "/" << (this->transactions).max_size() << "), transaction rejected from client: " << cid << KNRM << std::endl; } }
      } else { if (DEBUG0) { std::cout << KMAG << nfo() << "transaction rejected from stopped client: " << cid << KNRM << std::endl; } }
    } else { if (DEBUG0) { std::cout << KMAG << nfo() << "transaction rejected from unknown client: " << cid << KNRM << std::endl; } }
  } else { if (DEBUG1) std::cout << KMAG << nfo() << "discarded:" << msg.prettyPrint() << KNRM << std::endl; }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}


void Handler::handle_transaction(MsgTransaction msg, const ClientNet::conn_t &conn) {
  std::lock_guard<std::mutex> guard(mu_handle);
  handleTransaction(msg);
}


/*
void Handler::handleStart(MsgStart msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling(start):" << msg.prettyPrint() << KNRM << std::endl;
  if (verifyStart(msg)) {
    Transaction transaction = msg.trans;
    while ((this->transactions).size() < MAX_NUM_TRANSACTIONS) {
      this->transactions.push_back(transaction);
    }
    getStarted();
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded:" << msg.prettyPrint() << KNRM << std::endl;
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}*/


void Handler::handle_start(MsgStart msg, const ClientNet::conn_t &conn) {
  std::lock_guard<std::mutex> guard(mu_handle);
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;

  CID cid = msg.cid;

  if (this->clients.find(cid) == this->clients.end()) {
    (this->clients)[cid]=std::make_tuple(true,0,0,conn);
  }

  if (!this->started) {
    this->started=true;
    getStarted();
  }
}


/*void Handler::checkStopClients() {
  bool done = true;
  for (Clients::iterator it=this->clients.begin(); done && it!=this->clients.end(); ++it) {
    ClientNfo nfo = it->second;
    if (std::get<0>(nfo)) { done = false; }
  }
  if (done) {
    if (DEBUG0) std::cout << KMAG << nfo() << "stopping client event context" << KNRM << std::endl;
    cec.stop();
    stopped=true;
  }
}


void Handler::handle_stop(MsgStop msg, const ClientNet::conn_t &conn) {
  if (DEBUG0) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;

  CID cid = msg.cid;
  Clients::iterator it = this->clients.find(cid);
  if (it != this->clients.end()) { // we found an entry for 'cid'
    ClientNfo nfo = (ClientNfo)(it->second);
    (this->clients)[cid]=std::make_tuple(false,std::get<1>(nfo),std::get<2>(nfo));
    checkStopClients();
  }
}*/



// ----------------------------------------------
// -- Combined version
// --

Accum Handler::newviews2accComb(std::set<MsgNewViewComb> newviews) {
  // TODO: We don't quite need Justs here because we need only 1 signature
  Just justs[MAX_NUM_SIGNATURES]; // MAX_NUM_SIGNATURES is supposed to be == this->qsize

  RData rdata;
  Signs ss;

  unsigned int i = 0;
  for (std::set<MsgNewViewComb>::iterator it=newviews.begin(); it!=newviews.end() && i < MAX_NUM_SIGNATURES; ++it, i++) {
    MsgNewViewComb msg = (MsgNewViewComb)*it;
    if (i == 0) { rdata = msg.data; ss.add(msg.sign); } else { if (msg.data == rdata) { ss.add(msg.sign); } }
    justs[i] = Just(msg.data,msg.sign);
    if (DEBUG1) std::cout << KBLU << nfo() << "newview:" << msg.prettyPrint() << KNRM << std::endl;
    if (DEBUG1) std::cout << KBLU << nfo() << "just:" << justs[i].prettyPrint() << KNRM << std::endl;
  }

  Accum acc;
  if (ss.getSize() >= this->qsize) {
    // Then all the payloads are the same, in which case, we can use the simpler version of the accumulator
    if (DEBUG1) std::cout << KLGRN << nfo() << "newviews same(" << ss.getSize() << ")" << KNRM << std::endl;
    just_t just;
    just.set = 1;
    setRData(rdata,&just.rdata);
    setSigns(ss,&just.signs);
    acc = callTEEaccumCombSp(just);
  } else{
    if (DEBUG1) std::cout << KLRED << nfo() << "{comb} newviews diff (" << ss.getSize() << ")" << KNRM << std::endl;
    acc = callTEEaccumComb(justs);
  }

  return acc;
}


// For leader to begin a view (prepare phase) -- in the Comb mode
void Handler::prepareComb() {
  std::set<MsgNewViewComb> newviews = this->log.getNewViewComb(this->view,this->qsize);
  if (newviews.size() == this->qsize) {
    Accum acc = newviews2accComb(newviews);

    if (acc.isSet()) {
      // New block
      Block block = createNewBlock(acc.getPreph());

      // This one we'll store, and wait until we have this->qsize of them
      Just justPrep = callTEEprepareComb(block.hash(),acc);
      if (justPrep.isSet()) {
        if (DEBUG1) std::cout << KBLU << nfo() << "storing block for view=" << this->view << ":" << block.prettyPrint() << KNRM << std::endl;
        if (DEBUG1) std::cout << KBLU << nfo() << "storing block for view=" << this->view << ":" << block.hash().toString() << KNRM << std::endl;
        this->blocks[this->view]=block;

        MsgPrepareComb msgPrep(justPrep.getRData(),justPrep.getSigns());

        if (DEBUG1) std::cout << KBLU << nfo() << "ldr-prepare:" << msgPrep.signs.getSize() << KNRM << std::endl;
        if (msgPrep.signs.getSize() == 1) {
          Sign sig = msgPrep.signs.get(0);

          auto start = std::chrono::steady_clock::now();

          // This one goes to the backups
          MsgLdrPrepareComb msgLdrPrep(acc,block,sig);
          Peers recipients = remove_from_peers(this->myid);
          sendMsgLdrPrepareComb(msgLdrPrep,recipients);

          auto end = std::chrono::steady_clock::now();
          double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
          stats.addTotalLPrepTime(time);

          if (this->log.storePrepComb(msgPrep) == this->qsize) {
            preCommitComb(msgPrep.data);
          }
        }
      }
    } else {
      if (DEBUG2) std::cout << KBLU << nfo() << "bad accumulator" << acc.prettyPrint() << KNRM << std::endl;
    }
  }
}


// Run by the leader
void Handler::handleNewviewComb(MsgNewViewComb msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  View v = msg.data.getPropv();
  if (v >= this->view && amLeaderOf(v)) {
    if (this->log.storeNvComb(msg) == this->qsize && v == this->view) {
      prepareComb();
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded:" << msg.prettyPrint() << KNRM << std::endl;
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalNvTime(time);
}

void Handler::handle_newviewcomb(MsgNewViewComb msg, const PeerNet::conn_t &conn) {
  handleNewviewComb(msg);
}


// For backups to verify MsgLdrPrepareComb messages send by leaders
bool Handler::verifyLdrPrepareComb(MsgLdrPrepareComb msg) {
  Accum acc   = msg.acc;
  Block block = msg.block;
  RData rdataLdrPrep(block.hash(),acc.getView(),acc.getPreph(),acc.getPrepv(),PH1_PREPARE);
  Signs signs = Signs(msg.sign);
  return Sverify(signs,this->myid,this->nodes,rdataLdrPrep.toString());
}


// For backups to respond to correct MsgLdrPrepareComb messages received from leaders
void Handler::respondToLdrPrepareComb(Block block, Accum acc) {
  Just justPrep = callTEEprepareComb(block.hash(),acc);
  if (justPrep.isSet()) {
    if (DEBUG1) std::cout << KBLU << nfo() << "storing block for view=" << this->view << ":" << block.prettyPrint() << KNRM << std::endl;
    this->blocks[this->view]=block;

    MsgPrepareComb msgPrep(justPrep.getRData(),justPrep.getSigns());
    PID leader = getCurrentLeader();
    Peers recipients = keep_from_peers(leader);
    sendMsgPrepareComb(msgPrep,recipients);
  }
}


// Run by the backups in the prepare phase
void Handler::handleLdrPrepareComb(MsgLdrPrepareComb msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  Accum acc   = msg.acc;
  Block block = msg.block;
  View v      = acc.getView();
  Hash hash   = acc.getPreph();
  bool vm     = verifyLdrPrepareComb(msg);
  if (v >= this->view
      && !amLeaderOf(v)
      && vm
      && acc.getSize() == this->qsize
      && block.extends(hash)) {
    if (v == this->view) {
      respondToLdrPrepareComb(block,acc);
    } else {
      // If the message is for later, we store it
      if (DEBUG1) std::cout << KMAG << nfo() << "storing:" << msg.prettyPrint() << KNRM << std::endl;
      this->log.storeLdrPrepComb(msg);
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded:" << msg.prettyPrint() << KNRM << std::endl;
    if (DEBUG1) std::cout << KMAG << nfo() << "because:"
                          << "check-view=" << std::to_string(v >= this->view)
                          << ";check-leader=" << std::to_string(!amLeaderOf(v))
                          << ";verif-msg=" << std::to_string(vm)
                          << ";check-quorum=" << std::to_string(acc.getSize() == this->qsize)
                          << "(acc-size=" << std::to_string(acc.getSize()) << ",quorum-size=" << std::to_string(this->qsize) << ")"
                          << ";check-extends=" << std::to_string(block.extends(hash))
                          << KNRM << std::endl;
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  if (DEBUGT) std::cout << KMAG << nfo() << "MsgLdrPrepareComb3:" << time << KNRM << std::endl;
}

void Handler::handle_ldrpreparecomb(MsgLdrPrepareComb msg, const PeerNet::conn_t &conn) {
  if (DEBUGT) printNowTime(KBLU, "handling MsgLdrPrepareComb");
  handleLdrPrepareComb(msg);
}

// For backups to respond to MsgPrepareComb messages receveid from leaders
void Handler::respondToPrepareComb(MsgPrepareComb msg) {
  Just justPc = callTEEstoreComb(Just(msg.data,msg.signs));
  if (DEBUG1) { std::cout << KMAG << nfo() << "TEEstoreComb just:" << justPc.prettyPrint() << KNRM << std::endl; }
  MsgPreCommitComb msgPc(justPc.getRData(),justPc.getSigns());
  Peers recipients = keep_from_peers(getCurrentLeader());
  sendMsgPreCommitComb(msgPc,recipients);
}


// For leaders to send prepare certificates to backups at the beginning of the pre-commit phase
void Handler::preCommitComb(RData data) {
  Signs signs = (this->log).getPrepareComb(data.getPropv(),this->qsize);
  // We should not need to check the size of 'signs' as this function should only be called, when this is possible
  if (signs.getSize() == this->qsize) {
    MsgPrepareComb msgPrep(data,signs);
    Peers recipients = remove_from_peers(this->myid);
    sendMsgPrepareComb(msgPrep,recipients);

    // The leader also stores the prepare message
    Just justPc = callTEEstoreComb(Just(data,signs));
    MsgPreCommitComb msgPc(justPc.getRData(),justPc.getSigns());

    // We store our own commit in the log
    if (this->qsize <= this->log.storePcComb(msgPc)) {
      decideComb(justPc.getRData());
    }
  }
}


void Handler::handlePrepareComb(MsgPrepareComb msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  RData data = msg.data;
  View v = data.getPropv();
  if (v == this->view) {
    if (amLeaderOf(v)) {
      // Beginning of pre-commit phase, we store messages until we get enough of them to start pre-committing
      if (this->log.storePrepComb(msg) == this->qsize) {
        preCommitComb(data);
      }
    } else {
      // Backups wait for a MsgPrepareAcc message from the leader that contains qsize signatures in the pre-commit phase
      respondToPrepareComb(msg);
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "storing:" << msg.prettyPrint() << KNRM << std::endl;
    if (v > this->view) { log.storePrepComb(msg); }
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

void Handler::handle_preparecomb(MsgPrepareComb msg, const PeerNet::conn_t &conn) {
  handlePrepareComb(msg);
}


void Handler::handleEarlierMessagesComb() {
  // *** THIS IS FOR LATE NODES TO PRO-ACTIVELY PROCESS MESSAGES THEY HAVE ALREADY RECEIVED FOR THE NEW VIEW ***
  // We now check whether we already have enough information to start the next view if we're the leader
  if (amCurrentLeader()) {
    std::set<MsgNewViewComb> newviews = this->log.getNewViewComb(this->view,this->qsize);
    if (newviews.size() == this->qsize) {
      if (DEBUG1X) std::cout << KMAG << nfo() << "leader catching up (" << this->view << ")" << KNRM << std::endl;
      // we have enough new view messages to start the new view
      prepareComb();
    }
  } else {
    // First we check whether the view has already been locked
    // (i.e., we received a pre-commit certificate from the leader),
    // in which case we don't need to go through the previous steps.
    Signs signsPc = (this->log).getPrecommitComb(this->view,this->qsize);
    if (signsPc.getSize() == this->qsize) {
      if (DEBUG1X) std::cout << KMAG << nfo() << "catching up using pre-commit certificate (" << this->view << ")" << KNRM << std::endl;
      // We skip the prepare phase (this is otherwise a TEEprepareComb):
      callTEEsignComb();
      // We skip the pre-commit phase (this is otherwise a TEEstoreComb):
      callTEEsignComb();
      // We execute
      MsgPreCommitComb msgPc = this->log.firstPrecommitComb(this->view);
      respondToPreCommitComb(msgPc);
    } else { // We don't have enough pre-commit signatures
      Signs signsPrep = (this->log).getPrepareComb(this->view,this->qsize);
      if (signsPrep.getSize() == this->qsize) {
        if (DEBUG1X) std::cout << KMAG << nfo() << "catching up using prepare certificate (COMB) (" << this->view << ")" << KNRM << std::endl;
        // TODO: If we're late, we currently store two prepare messages (in the prepare phase,
        // the one from the leader with 1 sig; and in the pre-commit phase, the one with f+1 sigs.
        MsgPrepareComb msgPrep = this->log.firstPrepareComb(this->view);
        // We skip the prepare phase (this is otherwise a TEEprepare):
        callTEEsign();
        // We store the prepare certificate
        respondToPrepareComb(msgPrep);
      } else {
        MsgLdrPrepareComb msgProp = this->log.firstLdrPrepareComb(this->view);
        if (msgProp.sign.isSet()) { // If we've stored the leader's proposal
          if (DEBUG1X) std::cout << KMAG << nfo() << "catching up using leader proposal" << KNRM << std::endl;
          respondToLdrPrepareComb(msgProp.block,msgProp.acc);
        }
      }
    }
  }
}


// TODO: also trigger new-views when there is a timeout
void Handler::startNewViewComb() {
  Just just = callTEEsignComb();
  startNewViewCombOn(just);
}

void Handler::startNewViewCombOn(Just just) {
  // generate justifications until we can generate one for the next view
  while (just.getRData().getPropv() <= this->view) { just = callTEEsignComb(); }
  // increment the view
  // *** THE NODE HAS NOW MOVED TO THE NEW-VIEW ***
  this->view++;

  // We start the timer
  setTimer();

  // if the lastest justification we've generated is for what is now the current view (since we just incremented it)
  // and round 0, then send a new-view message
  if (just.getRData().getPropv() == this->view
      && just.getRData().getPhase() == PH1_NEWVIEW
      && just.getSigns().getSize() == 1) {
    MsgNewViewComb msg(just.getRData(),just.getSigns().get(0));
    if (amCurrentLeader()) {
      handleEarlierMessagesComb();
      handleNewviewComb(msg);
    }
    else {
      PID leader = getCurrentLeader();
      Peers recipients = keep_from_peers(leader);
      sendMsgNewViewComb(msg,recipients);
      handleEarlierMessagesComb();
    }
  } else {
    // Something wrong happened
  }
}



void Handler::executeComb(RData data) {
  auto endView = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(endView - startView).count();
  startView = endView;
  stats.incExecViews();
  stats.addTotalViewTime(time);
  if (this->transactions.empty()) { this->viewsWithoutNewTrans++; } else { this->viewsWithoutNewTrans = 0; }

  // Execute
  // TODO: We should wait until we received the block corresponding to the hash to execute
  if (DEBUG0 && DEBUGE) std::cout << KRED << nfo() << "COMB-EXECUTE(" << this->view << "/" << this->maxViews << ":" << time << ")" << stats.toString() << KNRM << std::endl;

  // Reply
  replyHash(data.getProph());

  if (timeToStop()) {
    recordStats();
  } else {
    startNewViewComb();
  }
}


// Checks that it contains qsize correct signatures
bool Handler::verifyPreCommitCombCert(MsgPreCommitComb msg) {
  Signs signs = msg.signs;
  if (signs.getSize() == this->qsize) {
    return Sverify(signs,this->myid,this->nodes,msg.data.toString());
  }
  return false;
}


// For leaders to send pre-commit certificates to backups at the beginning the decide phase
void Handler::decideComb(RData data) {
  View view = data.getPropv();
  Signs signs = (this->log).getPrecommitComb(view,this->qsize);
  if (signs.getSize() == this->qsize) {
    MsgPreCommitComb msgPc(data,signs);
    Peers recipients = remove_from_peers(this->myid);
    sendMsgPreCommitComb(msgPc,recipients);

    if (verifyPreCommitCombCert(msgPc)) {
      executeComb(data);
    }
  }
}


// For backups to respond to MsgPreCommitComb messages received from leaders
void Handler::respondToPreCommitComb(MsgPreCommitComb msg) {
  if (verifyPreCommitCombCert(msg)) {
    executeComb(msg.data);
  }
}


void Handler::handlePreCommitComb(MsgPreCommitComb msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  RData data = msg.data;
  View v = data.getPropv();
  if (v == this->view) {
    if (amLeaderOf(v)) {
      // Beginning of decide phase, we store messages until we get enough of them to start deciding
      if (this->log.storePcComb(msg) == this->qsize) {
        decideComb(data);
      }
    } else {
      // Backups wait for a MsgPreCommitComb message from the leader that contains qsize signatures in the decide phase
      respondToPreCommitComb(msg);
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "storing:" << msg.prettyPrint() << KNRM << std::endl;
    if (v > this->view) { log.storePcComb(msg); }
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalDecTime(time);
}

void Handler::handle_precommitcomb(MsgPreCommitComb msg, const PeerNet::conn_t &conn) {
  handlePreCommitComb(msg);
}




// ----------------------------------------------
// -- OP version
// --


// TODO
void Handler::handleEarlierMessagesOP() {
  auto start = std::chrono::steady_clock::now();

  if (!amCurrentLeader()) {
    if (DEBUG1) std::cout << KBLU << nfo() << "backup checking whether there are earlier messages to handle for view " << this->view << KNRM << std::endl;
    // check whether we already have a prepare message for the new view
    OPprepare prep = this->log.getOPprepare(this->view);
    if (prep.getAuths().getSize() == this->qsize) {
      if (DEBUG1X) std::cout << KMAG << nfo() << "catching up using pre-commit certificate (" << this->view << ")" << KNRM << std::endl;
      respondToPreCommitOP(prep);
    } else {
      // we don't have a prepare message yet but check whether we have a MsgLdrPrepareOP
      LdrPrepareOP prop = this->log.getLdrPrepareOp(this->view);
      if (prop.prop.getAuth().getHash().getSet()) {
        if (DEBUG1X) std::cout << KMAG << nfo() << "catching up using leader proposal (" << this->view << ")" << KNRM << std::endl;
        if (prop.tag == OPCacc) {
          respondToLdrPrepareOP(prop.block,prop.prop,OPcert(prop.vote));
        } else {
          respondToLdrPrepareOP(prop.block,prop.prop,OPcert(prop.prep));
        }
      } else {
        // We check whether we have a MsgLdrAddOP (its accumulator)
        OPaccum acc = this->log.getAccOp(this->view-1);
        if (acc.getSize() == this->qsize) {
          // Same code as in handleLdrAddOP
          OPvote vote = callTEEvoteOP(acc.getHash());
          PID leader = getCurrentLeader();
          Peers recipients = keep_from_peers(leader);
          sendMsgBckAddOP(vote,recipients);
        }
      }
    }
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "leader checking whether there are earlier messages to handle for view " << this->view << KNRM << std::endl;
    // as a leader we might be about to handle our own newviewB message, but we might have a newviewA message stored already
    OPprepare prep = this->log.getNvOpas(this->view-1); // the -1 is because the prepare for view v in a newview will have view v-1
    if (prep.getAuths().getSize() == this->qsize) {
      handleNewviewOP(prep);
    }
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalEarlyTime(time);
}


MsgNewViewOPB Handler::genMsgNewViewOPB() {
  auto start0 = std::chrono::steady_clock::now();

  Block block = (this->opprop).block;
  OPproposal prop = (this->opprop).prop;
  OPcert cert = (this->opprop).cert;

  // By this time we've already increased the view, so we're looking for stores at view view-1
  OPprepare prep = this->log.getOPstores(this->view-1,1);

  OPstore store;
  // don't store again if already stored
  if (prep.getAuths().getSize() == 1) {
    if (DEBUG1) std::cout << KBLU << nfo() << "genMsgNewViewOPB:no need to generate a new store, has one for " << (this->view-1) << KNRM << std::endl;
    store = OPstore(prep.getView(),prep.getHash(),prep.getV(),prep.getAuths().get(0));
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "genMsgNewViewOPB:generating a new store" << KNRM << std::endl;
    //auto start2 = std::chrono::steady_clock::now();
    store = callTEEstoreOP(prop);
    //auto end2 = std::chrono::steady_clock::now();
    //double time2 = std::chrono::duration_cast<std::chrono::microseconds>(end2 - start2).count();
    //stats.addTotalGen2Time(time2);
    this->log.storeStoreOp(store);
  }

  OPnvblock nv(block,OPnvcert(store,cert));
  //if (DEBUG1X) std::cout << KBLU << nfo() << "A" << KNRM << std::endl;
  //if (DEBUG1X) std::cout << KBLU << nfo() << block.prettyPrint() << KNRM << std::endl;
  auto start2 = std::chrono::steady_clock::now();
  MsgNewViewOPB msg(nv);
  auto end2 = std::chrono::steady_clock::now();
  double time2 = std::chrono::duration_cast<std::chrono::microseconds>(end2 - start2).count();
  stats.addTotalGen2Time(time2);
  //if (DEBUG1X) std::cout << KBLU << nfo() << "B" << KNRM << std::endl;

  auto end0 = std::chrono::steady_clock::now();
  double time0 = std::chrono::duration_cast<std::chrono::microseconds>(end0 - start0).count();
  stats.addTotalGen0Time(time0);

  return msg;
}


// A simpler version than genMsgNewViewOPBB for when we don't have to send the block
MsgNewViewOPBB Handler::genMsgNewViewOPBB() {
  auto start0 = std::chrono::steady_clock::now();

  Block block = (this->opprop).block;
  OPproposal prop = (this->opprop).prop;
  OPcert cert = (this->opprop).cert;

  // By this time we've already increased the view, so we're looking for stores at view view-1
  OPprepare prep = this->log.getOPstores(this->view-1,1);

  OPstore store;
  // don't store again if already stored
  if (prep.getAuths().getSize() == 1) {
    if (DEBUG1) std::cout << KBLU << nfo() << "genMsgNewViewOPBB:no need to generate a new store, has one for " << (this->view-1) << KNRM << std::endl;
    store = OPstore(prep.getView(),prep.getHash(),prep.getV(),prep.getAuths().get(0));
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "genMsgNewViewOPBB:generating a new store" << KNRM << std::endl;
    //auto start2 = std::chrono::steady_clock::now();
    store = callTEEstoreOP(prop);
    //auto end2 = std::chrono::steady_clock::now();
    //double time2 = std::chrono::duration_cast<std::chrono::microseconds>(end2 - start2).count();
    //stats.addTotalGen2Time(time2);
    this->log.storeStoreOp(store);
  }

  auto start2 = std::chrono::steady_clock::now();
  MsgNewViewOPBB msg(store,cert.prep);
  auto end2 = std::chrono::steady_clock::now();
  double time2 = std::chrono::duration_cast<std::chrono::microseconds>(end2 - start2).count();
  stats.addTotalGen2Time(time2);
  //if (DEBUG1X) std::cout << KBLU << nfo() << "B" << KNRM << std::endl;

  auto end0 = std::chrono::steady_clock::now();
  double time0 = std::chrono::duration_cast<std::chrono::microseconds>(end0 - start0).count();
  stats.addTotalGen0Time(time0);

  return msg;
}


void Handler::startNewViewOPA(OPprepare prep) {
  if (DEBUG1) std::cout << KBLU << nfo() << "onep" << KNRM << std::endl;
  MsgNewViewOPA msg(prep);

  if (amCurrentLeader()) {
    handleEarlierMessagesOP();
    handleNewviewOP(msg);
  }
  else {
    PID leader = getCurrentLeader();
    Peers recipients = keep_from_peers(leader);
    sendMsgNewViewOP(msg,recipients);
    handleEarlierMessagesOP();
  }
}


void Handler::startNewViewOPB() {
  auto start = std::chrono::steady_clock::now();

  // We're checking here whether we have a this->opprop with a certificate for the block
  // that was signed by the leader so that we don't have to re-send the block to that node as it has it already
  if (this->opprop.cert.tag == OPCprep
      && this->opprop.cert.prep.getView() == this->opprop.cert.prep.getV()
      && this->opprop.prop.getView() == this->opprop.cert.prep.getView()
      && this->opprop.cert.prep.getAuths().hasSigned(getCurrentLeader())) {
    if (DEBUG1) std::cout << KBGRN << nfo() << "no need to send block in newview: "
                          << getCurrentLeader() << "-"
                          << this->opprop.cert.prep.getAuths().prettyPrint() << "-"
                          << this->opprop.prettyPrint()
                          << KNRM << std::endl;

    if (DEBUG1) std::cout << KBLU << nfo() << "onepbb" << KNRM << std::endl;
    MsgNewViewOPBB msg = genMsgNewViewOPBB();

    if (amCurrentLeader()) {
      if (DEBUG1) std::cout << KBLU << nfo() << "current leader of view " << this->view << KNRM << std::endl;
      handleEarlierMessagesOP();
      handleNewviewOP(msg);
    }
    else {
      if (DEBUG1) std::cout << KBLU << nfo() << "NOT current leader of view " << this->view << KNRM << std::endl;
      PID leader = getCurrentLeader();
      Peers recipients = keep_from_peers(leader);
      sendMsgNewViewOP(msg,recipients);
      handleEarlierMessagesOP();
    }

  } else {

    if (DEBUG1) std::cout << KBLU << nfo() << "onepb" << KNRM << std::endl;
    MsgNewViewOPB msg = genMsgNewViewOPB();

    if (amCurrentLeader()) {
      if (DEBUG1) std::cout << KBLU << nfo() << "current leader of view " << this->view << KNRM << std::endl;
      handleEarlierMessagesOP();
      handleNewviewOP(msg);
    }
    else {
      if (DEBUG1) std::cout << KBLU << nfo() << "NOT current leader of view " << this->view << KNRM << std::endl;
      PID leader = getCurrentLeader();
      Peers recipients = keep_from_peers(leader);
      sendMsgNewViewOP(msg,recipients);
      handleEarlierMessagesOP();
    }

  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalStartTime(time);
}


void Handler::startNewViewOnTimeoutOP() {
  if (DEBUG1) std::cout << KBLU << nfo() << "starting a new view on timeout" << KNRM << std::endl;

  // increase view
  this->view++;

  // restart the timer
  setTimer();

  // send new-view messages + catch-up
  startNewViewOPB();
}


void Handler::startNewViewOP() {
  if (DEBUG1) std::cout << KBLU << nfo() << "starting a new view" << "(current=" << this->view << "; moving to=" << this->view+1 << ")" << KNRM << std::endl;

  OPprepare prep = this->opprep;
  if (DEBUG1) std::cout << KBLU << nfo() << "new-view cert (" << prep.getView() << "," << this->view << ")" << KNRM << std::endl;
  // generate justifications until we can generate one for the next view
  //  while (prep.getView() < this->view) {
  //    if (DEBUG1) std::cout << KBLU << nfo() << "TODO" << "(startNewViewOP)" << KNRM << std::endl;
  //    exit(0);
  //    // TODO
  //  }
  // increment the view
  // *** THE NODE HAS NOW MOVED TO THE NEW-VIEW ***
  this->view++;

  // We start the timer
  setTimer();

  // if the lastest justification we've generated is for what is now the current view (since we just incremented it)
  // and round 0, then send a new-view message
  if (prep.getView() == this->view - 1) {
    if (DEBUG1) std::cout << KBLU << nfo() << "start-new-view:ok" << KNRM << std::endl;
    startNewViewOPA(prep);

  } else {
    if (DEBUG1) std::cout << KBLU << nfo()
                           << "start-new-view:don't have the latest prepare certificate(prep="
                           << prep.getView() << ",curr=" << this->view << ")"
                           << KNRM << std::endl;
    // Something wrong happened
    startNewViewOPB();
  }
}


void Handler::preCommitOP(View v) {
  auto start = std::chrono::steady_clock::now();

  OPprepare cert = this->log.getOPstores(v,this->qsize);
  if (DEBUG1) { std::cout << KGRN << "prepare-cert:" << cert.prettyPrint() << KNRM << std::endl; }
  if (cert.getView() == cert.getV() && cert.getAuths().getSize() == this->qsize) {
    MsgPreCommitOP msg(cert);
    Peers recipients = remove_from_peers(this->myid);
    sendMsgPreCommitOP(msg,recipients);

    if ((this->opprop).prop.getView() == cert.getView()) {
      this->opprop=OPprp((this->opprop).block,(this->opprop).prop,cert);
    }

    this->opprep = cert;
    executeOP(cert);
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalPCommTime(time);
}


// For leader to begin a view (prepare phase) -- in the OP mode
void Handler::prepareOp(OPprepare prep) {
  if (DEBUG1) std::cout << KBLU << nfo() << "in prepareOp" << KNRM << std::endl;
  auto start = std::chrono::steady_clock::now();

  if (DEBUG1) std::cout << KBLU << nfo() << "leader preparing (prepareOp)" << KNRM << std::endl;
  Block block = createNewBlock(prep.getHash());
  Hash hash = block.hash();

  // This one we'll store, and wait until we have this->qsize of them
  OPproposal prop = callTEEprepareOP(hash);
  if (DEBUG1) std::cout << KBLU << nfo() << "generated proposal:" << prop.prettyPrint() << KNRM << std::endl;

  if (prop.getView() != this->view) {
    if (DEBUG1) std::cout << KBRED << nfo() << "bad proposal view (prepareOp):prop=" << prop.getView() << ",curr=" << this->view << KNRM << std::endl;
  }

  if (prop.getAuth().getHash().getSet()) {
    if (DEBUG1) std::cout << KBLU << nfo() << "storing block for view=" << this->view << ":" << block.prettyPrint() << KNRM << std::endl;
    if (DEBUG1) std::cout << KBLU << nfo() << "storing block for view=" << this->view << ":" << hash.toString() << KNRM << std::endl;
    this->blocks[this->view]=block;
    this->prepared[this->view]=true;

    // This one goes to the backups
    MsgLdrPrepareOPA msgLdrPrep(block,prop,prep);
    Peers recipients = remove_from_peers(this->myid);
    sendMsgLdrPrepareOPA(msgLdrPrep,recipients);

    this->opprop = OPprp(block,prop,OPcert(prep));
    OPstore store = callTEEstoreOP(prop);

    if (this->log.storeStoreOp(store) == this->qsize) {
      if (DEBUG1) std::cout << KBLU << nfo() << "stored..." << KNRM << std::endl;
      preCommitOP(store.getView());
    }
    if (DEBUG1) std::cout << KBLU << nfo() << "prepareOp done" << KNRM << std::endl;
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "prepareOp failed" << KNRM << std::endl;
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalLPrepTime(time);
}


// For leader to begin a view (prepare phase) -- in the OP mode
void Handler::prepareOp_debug(OPprepare prep) {
  if (DEBUG1) std::cout << KBLU << nfo() << "leader preparing (prepareOp)" << KNRM << std::endl;

  //Block block = createNewBlock();
  // BEGIN createNewBlock
  Transaction trans[MAX_NUM_TRANSACTIONS];
  Block block1(0,Hash(),0,trans);
  // END createNewBlock
  Block block2(0,Hash(),0,trans);

  // Crashes with the line below which has nothing to do with the above...
  //MsgLdrPrepareOPA msgLdrPrep(0); //(block,prop,prep,true); // p8b segfaults for payload=2048..
}


// For leaders to begin the prepare phase when the accumulator is for a OPstore certified by an OPprepare certificate
// THIS IS NOT USED ANYMORE
void Handler::prepareOpAcc(OPaccum acc, OPstore store, OPprepare prep) {
  auto start = std::chrono::steady_clock::now();

  if (DEBUG1) std::cout << KBLU << nfo() << "leader preparing (prepareOpAcc)" << KNRM << std::endl;
  Block block = createNewBlock(acc.getHash());
  Hash hash = block.hash();

  // This one we'll store, and wait until we have this->qsize of them
  OPproposal prop = callTEEprepareOP(hash);
  if (DEBUG1) std::cout << KBLU << nfo() << "generated proposal:" << prop.prettyPrint() << KNRM << std::endl;

  if (prop.getView() != this->view) {
    if (DEBUG1) std::cout << KBRED << nfo() << "bad proposal view (prepareOpAcc):" << prop.getView() << "," << this->view << KNRM << std::endl;
  }

  if (prop.getAuth().getHash().getSet()) {
    if (DEBUG1) std::cout << KBLU << nfo() << "storing block for view=" << this->view << ":" << block.prettyPrint() << KNRM << std::endl;
    if (DEBUG1) std::cout << KBLU << nfo() << "storing block for view=" << this->view << ":" << hash.toString() << KNRM << std::endl;
    this->blocks[this->view]=block;
    this->prepared[this->view]=true;

    // This one goes to the backups
    MsgLdrPrepareOPB msgLdrPrep(block,prop,acc,prep);
    Peers recipients = remove_from_peers(this->myid);
    sendMsgLdrPrepareOPB(msgLdrPrep,recipients);

    this->opprop = OPprp(block,prop,OPcert(prep));
    OPstore store = callTEEstoreOP(prop);

    if (this->log.storeStoreOp(store) == this->qsize) {
      if (DEBUG1) std::cout << KBLU << nfo() << "stored..." << KNRM << std::endl;
      preCommitOP(store.getView());
    }
    if (DEBUG1) std::cout << KBLU << nfo() << "prepareOp done" << KNRM << std::endl;
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "prepareOp failed" << KNRM << std::endl;
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalLPrepTime(time);
}



// For leaders to begin the prepare phase when getting a vote certificate from the additional phase
void Handler::prepareOpVote(OPvote vote) {
  auto start = std::chrono::steady_clock::now();

  if (DEBUG1) std::cout << KBLU << nfo() << "leader preparing (prepareOpVote)" << KNRM << std::endl;
  Block block = createNewBlock(vote.getHash());
  Hash hash = block.hash();

  // This one we'll store, and wait until we have this->qsize of them
  OPproposal prop = callTEEprepareOP(hash);
  if (DEBUG1) std::cout << KBLU << nfo() << "generated proposal:" << prop.prettyPrint() << KNRM << std::endl;

  if (prop.getView() != this->view) {
    if (DEBUG1) std::cout << KBRED << nfo() << "bad proposal view (prepareOpVote):" << prop.getView() << "," << this->view << KNRM << std::endl;
  }

  if (prop.getAuth().getHash().getSet()) {
    if (DEBUG1) std::cout << KBLU << nfo() << "storing block for view=" << this->view << ":" << block.prettyPrint() << KNRM << std::endl;
    if (DEBUG1) std::cout << KBLU << nfo() << "storing block for view=" << this->view << ":" << hash.toString() << KNRM << std::endl;
    this->blocks[this->view]=block;
    this->prepared[this->view]=true;

    // This one goes to the backups
    MsgLdrPrepareOPC msgLdrPrep(block,prop,vote);
    Peers recipients = remove_from_peers(this->myid);
    sendMsgLdrPrepareOPC(msgLdrPrep,recipients);

    this->opprop = OPprp(block,prop,OPcert(vote));
    OPstore store = callTEEstoreOP(prop);

    if (this->log.storeStoreOp(store) == this->qsize) {
      if (DEBUG1) std::cout << KBLU << nfo() << "stored..." << KNRM << std::endl;
      preCommitOP(store.getView());
    }
    if (DEBUG1) std::cout << KBLU << nfo() << "prepareOp done" << KNRM << std::endl;
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "prepareOp failed" << KNRM << std::endl;
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalLPrepTime(time);
}


// Run by the leader - called by handleNewviewOP on a MsgNewViewOPA
void Handler::handleNewviewOP(OPprepare prep) {
  View v = prep.getView();
  // The leader of view v+1 collects messages from view v (or we're handling the initial view)
  if (v+1 >= this->view && amLeaderOf(v+1)) {
    if (v+1 == this->view
        && this->blocks.find(this->view) == this->blocks.end()) {
        //&& this->prepared.find(this->view) == this->prepared.end()) {
      // By checking that this->prepared[this->view] does not contain anything we ensure that we don't
      // start preparing again even when we have started preparing with the slower phases
      if (DEBUG1) std::cout << KBLU << nfo() << "preparing " << this->view << KNRM << std::endl;
      prepareOp(prep);
    } else {
      if (DEBUG1) std::cout << KBLU << nfo()
                            << "not preparing (prep view=" << v
                            << ";curr view=" << this->view
                            << ";bool1=" << std::to_string(v+1 == this->view)
                            << ";bool2=" << std::to_string(this->blocks.find(this->view) == this->blocks.end())
                            << ")"
                            << KNRM << std::endl;
      if (v+1 > this->view) {
        if (DEBUG1) std::cout << KBLU << nfo() << "storing new-view for later" << KNRM << std::endl;
        this->log.storeNvOp(prep);
        if (DEBUG1) std::cout << KBLU << nfo() << "stored new-view" << KNRM << std::endl;
      }
    }
    if (DEBUG1) std::cout << KBLU << nfo() << "handled new-view" << KNRM << std::endl;
  } else if (v == 0 && this->view == 0 && amLeaderOf(0) && this->blocks.find(this->view) == this->blocks.end()) {
    // special case of the initial view
    if (DEBUG1) std::cout << KBLU << nfo() << "preparing for initial view " << KNRM << std::endl;
    prepareOp(prep);
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded:" <<  this->view << "-" << prep.prettyPrint() << KNRM << std::endl;
  }
}


// Run by the leader
void Handler::handleNewviewOP(MsgNewViewOPA msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;

  handleNewviewOP(msg.prep);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalNvTime(time);
}


OPnvblock Handler::highestNewViewOpb(std::set<OPnvblock> *newviews) {
  std::set<OPnvblock>::iterator it0=newviews->begin();
  if (DEBUG5) std::cout << KBLU << nfo() << "highest-size1:" << newviews->size() << KNRM << std::endl;
  OPnvblock highest = (OPnvblock)*it0;
  for (std::set<OPnvblock>::iterator it = it0; it!=newviews->end(); ++it) {
    OPnvblock msg = (OPnvblock)*it;
    if (msg.cert.store.getV() > highest.cert.store.getV()) { it0 = it; highest = msg; }
  }
  newviews->erase(it0);
  if (DEBUG5) std::cout << KBLU << nfo() << "highest-size2:" << newviews->size() << KNRM << std::endl;
  return highest;
}


OPaccum Handler::newviews2accOp(OPnvblock high, std::set<OPnvcert> others) {
  OPstore justs[MAX_NUM_SIGNATURES-1];
  Auths ss(high.cert.store.getAuth());
  OPstore data = high.cert.store;

  unsigned int i = 0;
  for (std::set<OPnvcert>::iterator it=others.begin(); it!=others.end() && i < MAX_NUM_SIGNATURES-1; ++it, i++) {
    OPnvcert msg = (OPnvcert)*it;
    if (msg.store.getView() == data.getView()
        && msg.store.getHash() == data.getHash()
        && msg.store.getV() == data.getV()) {
      if (DEBUG1) std::cout << KBLU << nfo() << "adding:" << msg.store.getAuth().prettyPrint() << KNRM << std::endl;
      ss.add(msg.store.getAuth());
    }
    justs[i] = msg.store;
    if (DEBUG1) std::cout << KBLU << nfo() << "newview:" << msg.prettyPrint() << KNRM << std::endl;
    if (DEBUG1) std::cout << KBLU << nfo() << "just:" << justs[i].prettyPrint() << KNRM << std::endl;
  }

  OPaccum acc;
  if (ss.getSize() >= this->qsize) {
    // Then all the payloads are the same, in which case, we can use the simpler version of the accumulator
    if (DEBUG1) std::cout << KLGRN << nfo() << "newviews same(" << ss.getSize() << ")" << KNRM << std::endl;
    OPprepare p(data.getView(),data.getHash(),data.getV(),ss);
    acc = callTEEaccumOpSp(p);
  } else{
    if (DEBUG1) std::cout << KLRED << nfo() << "{op} newviews diff (" << ss.getSize() << ")" << KNRM << std::endl;
    acc = callTEEaccumOp(data,justs);
  }

  return acc;
}


OPprepare nvSameStores(OPnvblock nv, std::set<OPnvcert> nvs, unsigned int n) {
  View view = nv.cert.store.getView();
  Hash hash = nv.cert.store.getHash();
  View v    = nv.cert.store.getV();

  Auths auths(nv.cert.store.getAuth());
  std::set<PID> signers;
  signers.insert(nv.cert.store.getAuth().getId());

  for (std::set<OPnvcert>::iterator it=nvs.begin(); auths.getSize() < n && it!=nvs.end(); ++it) {
    OPnvcert nv1 = (OPnvcert)*it;
    if (view == nv1.store.getView()
        && hash == nv1.store.getHash()
        && v == nv1.store.getV()
        && signers.find(nv1.store.getAuth().getId()) == signers.end()) {
      auths.add(nv1.store.getAuth());
      signers.insert(nv1.store.getAuth().getId());
    }
  }

  return OPprepare(view,hash,v,auths);
}


// Run by leaders on new-view
void Handler::prepareOpb(View v) {
  auto start = std::chrono::steady_clock::now();

  // !!!!!!!!!!!!!!!!!!!!!!!!!!
  //Transaction trans[MAX_NUM_TRANSACTIONS];

  if (DEBUG1) std::cout << KBLU << nfo() << "leader preparing " << this->view << KNRM << std::endl;
  if (v+1 == this->view) {
    OPnvblocks nvs = this->log.getNvOpbs(v); //, this->qsize
    if (DEBUG1) std::cout << KBLU << nfo() << "nvblocks:" << nvs.prettyPrint() << KNRM << std::endl;
    if (nvs.certs.certs.size() + 1 >= this->qsize) {
      //OPnvblock highest = nvs.nv; //highestNewViewOpb(&nvs);
      OPprepare maybePrep = nvSameStores(nvs.nv,nvs.certs.certs,this->qsize);

      if (DEBUG1) std::cout << KBLU << nfo() << "maybePrep:" << maybePrep.prettyPrint() << KNRM << std::endl;

      unsigned int opcase = 0;

      if (opcase <=1 && nvs.nv.cert.store.getView() == this->view-1 && maybePrep.getAuths().getSize() == this->qsize) {
        stats.incNumOnePBs();

        if (DEBUG1) std::cout << KBLU << nfo() << "prepareOpb(1a)" << KNRM << std::endl;
        prepareOp(maybePrep);
        if (DEBUG1) std::cout << KBLU << nfo() << "prepareOpb(1b)" << KNRM << std::endl;
      } else {
        stats.incNumOnePCs();

        if (DEBUG1) std::cout << KBLU << nfo() << "newviews2accop" << KNRM << std::endl;
        OPaccum acc = newviews2accOp(nvs.nv,nvs.certs.certs);
        if (DEBUG1) std::cout << KBLU << nfo() << "acc=" << acc.prettyPrint() << KNRM << std::endl;

        if (acc.isSet()) {
//          if (opcase <= 2 && highest.cert.tag == OPCprep) {
//            if (DEBUG1) std::cout << KBLU << nfo() << "prepareOpb(2)" << KNRM << std::endl;
//            prepareOpAcc(acc,highest.store,highest.cert.prep);
//          } else {
            // Start the additional phase
            this->prepared[this->view]=false;
            if (DEBUG1) std::cout << KBLU << nfo() << "prepareOpb(2)" << KNRM << std::endl;
            MsgLdrAddOP msg(acc,nvs.nv);
            Peers recipients = remove_from_peers(this->myid);
            sendMsgLdrAddOP(msg,recipients);

            // We also record our own vote - similar code to
            //   - the core run by backups in handleLdrAddOP (to generate a vote)
            //   - and the code run the by leader (the current node) in handleBckAddOP (to handle a vote)
            // This is the first vote so there is not need to check whether we have enough - we don't
            OPvote vote = callTEEvoteOP(acc.getHash());
            unsigned int m = 0;
            this->log.storeVoteOp(vote,&m);
//          }
        }
      }
    }
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "leader not preparing, wrong view: " << v << "," << this->view << KNRM << std::endl;
  }

  if (DEBUG1) std::cout << KBLU << nfo() << "finished prepareOpb" << KNRM << std::endl;

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalLPrepbTime(time);
}


// Run by leaders
void Handler::handleNewviewOP(MsgNewViewOPB msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;

  // !!!!!!!!!!!!!!!!!!!!!!!!!!
  //Transaction* trans = new Transaction[MAX_NUM_TRANSACTIONS];
  //delete [] trans;
  //std::array<Transaction,MAX_NUM_TRANSACTIONS> trans;
  //std::array<Transaction,0> trans; // this works but not the above

  View v = msg.nv.cert.store.getView();
  // The leader of view v+1 collects messages from view v (or we're handling the initial view)
  if (v+1 >= this->view && amLeaderOf(v+1)) {

    unsigned int n = this->log.storeNvOp(msg.nv);
    if (v+1 == this->view) {
      if (this->prepared.find(this->view) == this->prepared.end()) { // i.e., if hasn't prepared this->view yet
        if (n >= this->qsize) {
          //this->blocks.find(this->view) == this->blocks.end()) {
          if (DEBUG1) std::cout << KBLU << nfo() << "handleNewviewOPB:preparing view " << this->view << KNRM << std::endl;
          prepareOpb(v);
        } else {
          if (DEBUG1) std::cout << KBLU << nfo()
                                << "handleNewviewOPB:not the exact number of signatures" << "(" << n << "/" << this->qsize << ")"
                                << KNRM << std::endl;
        }
      } else {
        if (DEBUG1) std::cout << KBLU << nfo()
                              << "handleNewviewOPB:already prepared view " << this->view
                              << KNRM << std::endl;
      }
    } else {
      if (DEBUG1) std::cout << KBLU << nfo()
                            << "handleNewviewOPB:wrong view" << "(store=" << v << ";current=" << this->view << ")"
                            << KNRM << std::endl;
    }
/*
    if (v+1 == this->view && this->blocks.find(this->view) == this->blocks.end()) {
      if (DEBUG1) std::cout << KBLU << nfo() << "preparing" << KNRM << std::endl;
      prepareOp(msg.prep);
    } else {
      if (DEBUG1) std::cout << KBLU << nfo() << "not preparing" << KNRM << std::endl;
      if (v+1 > this->view) {
        if (DEBUG1) std::cout << KBLU << nfo() << "storing new-view for later" << KNRM << std::endl;
        this->log.storeNvOp(msg);
        if (DEBUG1) std::cout << KBLU << nfo() << "stored new-view" << KNRM << std::endl;
      }
    }
    if (DEBUG1) std::cout << KBLU << nfo() << "handled new-view" << KNRM << std::endl;
*/

  } else if (v == 0 && this->view == 0 && amLeaderOf(0) && this->blocks.find(this->view) == this->blocks.end()) {
    // special case of the initial view
    if (DEBUG0) std::cout << KBLU << nfo() << "preparing for initial view " << KNRM << std::endl;
    prepareOp(this->opprep);
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded:received=" << v << ":current=" << this->view << "-" << msg.prettyPrint() << KNRM << std::endl;
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalNvTime(time);
}


void Handler::handleNewviewOP(MsgNewViewOPBB msg) {
  std::map<View,Block>::iterator it = this->blocks.find(msg.prep.getView());
  if (it != this->blocks.end()) {
    Block block = (Block)it->second;
    handleNewviewOP(MsgNewViewOPB(OPnvblock(block,OPnvcert(msg.store,OPcert(msg.prep)))));
  } else {
    if (DEBUG0) std::cout << KBRED << nfo() << "handleNewviewOP:MsgNewViewOPBB:missing block" << KNRM << std::endl;
  }
}

void Handler::handle_newviewopa(MsgNewViewOPA msg, const PeerNet::conn_t &conn) {
  std::lock_guard<std::mutex> guard(mu_handle);
  handleNewviewOP(msg);
}


void Handler::handle_newviewopb(MsgNewViewOPB msg, const PeerNet::conn_t &conn) {
  std::lock_guard<std::mutex> guard(mu_handle);
  handleNewviewOP(msg);
}


void Handler::handle_newviewopbb(MsgNewViewOPBB msg, const PeerNet::conn_t &conn) {
  std::lock_guard<std::mutex> guard(mu_handle);
  handleNewviewOP(msg);
}


// For backups to verify MsgLdrPrepareOP messages send by leaders
bool Handler::verifyLdrPrepareOP(MsgLdrPrepareOPA msg) {
  Block      block = msg.block;
  OPproposal prop  = msg.prop;
  OPprepare  prep  = msg.prep;
  std::string s1 = prop.data();
  std::string s2 = prep.data();
  // Proposal:
  Auths auths(prop.getAuth());
  bool b1     = callTEEverifyOP(auths,s1);
  // Prepare:
  bool b2     = callTEEverifyOP(prep.getAuths(),s2);
  if (DEBUG1) std::cout << KLBLU << nfo() << "verifying ldr-prepare:" << b1 << "(" << s1.size() << ")-" << b2 << "(" << s2.size() << ")" << KNRM << std::endl;
  //if (DEBUG1) std::cout << KLBLU << nfo() << "verifying ldr-prepare (prep-hash:" << sh.size() << "):" << sh << KNRM << std::endl;
  //if (DEBUG1) std::cout << KLBLU << nfo() << "verifying ldr-prepare (prep-view):" << view << KNRM << std::endl;
  return b1 && b2;
}


// For backups to verify MsgLdrPrepareOP messages send by leaders
bool Handler::verifyLdrPrepareOP(MsgLdrPrepareOPB msg) {
  Block      block = msg.block;
  OPproposal prop  = msg.prop;
  OPaccum    acc   = msg.acc;
  OPprepare  prep  = msg.prep;
  // Proposal:
  std::string s1 = prop.data();
  Auths auths1(prop.getAuth());
  bool b1 = callTEEverifyOP(auths1,s1);
  // Prepare:
  std::string s2 = acc.data();
  Auths auths2(acc.getAuth());
  bool b2 = callTEEverifyOP(auths2,s2);
  // Prepare:
  std::string s3 = prep.data();
  bool b3 = callTEEverifyOP(prep.getAuths(),s3);
  if (DEBUG1) std::cout << KLBLU << nfo() << "verifying ldr-prepare:" << b1 << "(" << s1.size() << ")-" << b2 << "(" << s2.size() << ")" << b3 << "(" << s3.size() << ")" << KNRM << std::endl;
  //if (DEBUG1) std::cout << KLBLU << nfo() << "verifying ldr-prepare (prep-hash:" << sh.size() << "):" << sh << KNRM << std::endl;
  //if (DEBUG1) std::cout << KLBLU << nfo() << "verifying ldr-prepare (prep-view):" << view << KNRM << std::endl;
  return b1 && b2 && b3;
}


// For backups to verify MsgLdrPrepareOP messages send by leaders
bool Handler::verifyLdrPrepareOP(MsgLdrPrepareOPC msg) {
  Block      block = msg.block;
  OPproposal prop  = msg.prop;
  OPvote     vote  = msg.vote;
  std::string s1 = prop.data();
  std::string s2 = vote.data();
  // Proposal:
  Auths auths(prop.getAuth());
  bool b1     = callTEEverifyOP(auths,s1);
  // Prepare:
  bool b2     = callTEEverifyOP(vote.getAuths(),s2);
  if (DEBUG1) std::cout << KLBLU << nfo() << "verifying ldr-prepare:" << b1 << "(" << s1.size() << ")-" << b2 << "(" << s2.size() << ")" << KNRM << std::endl;
  //if (DEBUG1) std::cout << KLBLU << nfo() << "verifying ldr-prepare (prep-hash:" << sh.size() << "):" << sh << KNRM << std::endl;
  //if (DEBUG1) std::cout << KLBLU << nfo() << "verifying ldr-prepare (prep-view):" << view << KNRM << std::endl;
  return b1 && b2;
}


// For backups to respond to correct MsgLdrPrepareOP messages received from leaders
void Handler::respondToLdrPrepareOP(Block block, OPproposal prop, OPcert cert) {
  this->blocks[this->view]=block;

  this->opprop = OPprp(block,prop,cert);
  OPstore store = callTEEstoreOP(prop);

  if (store.getView() == store.getV()) {
    this->log.storeStoreOp(store);

    MsgBckPrepareOP msg(store);
    PID leader = getCurrentLeader();
    Peers recipients = keep_from_peers(leader);
    sendMsgBckPrepareOP(msg,recipients);
  } else {
    if (DEBUG1) std::cout << KBRED << nfo()
                          << "bad store view (respondToLdrPrepareOP):storeView=" << store.getView()
                          << ",storeV=" << store.getV()
                          << ",curr=" << this->view
                          << KNRM << std::endl;
  }
}



// Run by the backups in the prepare phase
void Handler::handleLdrPrepareOP(MsgLdrPrepareOPA msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling(A):" << msg.prettyPrint() << KNRM << std::endl;
  Block block     = msg.block;
  OPproposal prop = msg.prop;
  OPprepare prep  = msg.prep;
  View v      = prop.getView();
  View v1     = prep.getView();
  View v2     = prep.getV();
  bool vm     = verifyLdrPrepareOP(msg);
  if (v >= this->view
      && v1 >= v2 // TO DOUBLE CHECK: was v1 == v2
      && (v1 == v - 1 || (v == 0 && v1 == 0)) // handling the initial view
      && !amLeaderOf(v)
      && getLeaderOf(v) == prop.getAuth().getId()
      && vm
      && block.extends(prep.getHash())
      && prop.getHash() == block.hash()) {
    if (v == this->view) {
      respondToLdrPrepareOP(block,prop,OPcert(prep));
    } else {
      // If the message is for later, we store it
      if (DEBUG1) std::cout << KMAG << nfo() << "storing(A):" << msg.prettyPrint() << KNRM << std::endl;
      this->log.storeLdrPrepOp(msg);
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded(A):" << msg.prettyPrint() << KNRM << std::endl;
    if (DEBUG1) std::cout << KMAG << nfo() << "because(A):"
                          << "check-view1=" << std::to_string(v >= this->view)
                          << ";check-view2=" << std::to_string(v1 >= v2)
                          << ";check-view3=" << std::to_string(v1 == v - 1 || (v == 0 && v1 == 0)) << "(" << v1 << "," << v << ")"
                          << ";check-leader1=" << std::to_string(!amLeaderOf(v)) << "(" << v << ")"
                          << ";check-leader2=" << std::to_string(getCurrentLeader() == prop.getAuth().getId())
                          << ";verif-msg=" << std::to_string(vm)
                          << ";check-extends=" << std::to_string(block.extends(prep.getHash()))
                          << ";check-hash=" << std::to_string(prop.getHash() == block.hash())
                          << KNRM << std::endl;
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalBPrepaTime(time);
}


void Handler::handleLdrPrepareOP(MsgLdrPrepareOPB msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling(B):" << msg.prettyPrint() << KNRM << std::endl;
  Block      block = msg.block;
  OPproposal prop  = msg.prop;
  OPaccum    acc   = msg.acc;
  OPprepare  prep  = msg.prep;
  View v      = prop.getView();
  View v1     = prep.getView();
  View v2     = prep.getV();
  bool vm     = verifyLdrPrepareOP(msg);
  if (v >= this->view
      && v1 == v2
      && (v1 == v - 1 || (v == 0 && v1 == 0)) // handling the initial view
      && !amLeaderOf(v)
      && getLeaderOf(v) == prop.getAuth().getId()
      && vm
      && block.extends(prep.getHash())
      && prop.getHash() == block.hash()
      // check that acc and prep match
      && (v1 == acc.getView() && prep.getHash() == acc.getHash())) {
    if (v == this->view) {
      respondToLdrPrepareOP(block,prop,OPcert(prep));
    } else {
      // If the message is for later, we store it
      if (DEBUG1) std::cout << KMAG << nfo() << "storing(B):" << msg.prettyPrint() << KNRM << std::endl;
      this->log.storeLdrPrepOp(msg);
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded(B):" << msg.prettyPrint() << KNRM << std::endl;
    if (DEBUG1) std::cout << KMAG << nfo() << "because(B):"
                          << "check-view1=" << std::to_string(v >= this->view)
                          << ";check-view2=" << std::to_string(v1 == v2)
                          << ";check-view3=" << std::to_string(v1 == v - 1 || (v == 0 && v1 == 0)) << "(" << v1 << "," << v << ")"
                          << ";check-leader1=" << std::to_string(!amLeaderOf(v)) << "(" << v << ")"
                          << ";check-leader2=" << std::to_string(getCurrentLeader() == prop.getAuth().getId())
                          << ";verif-msg=" << std::to_string(vm)
                          << ";check-extends=" << std::to_string(block.extends(prep.getHash()))
                          << ";check-hash=" << std::to_string(prop.getHash() == block.hash())
                          << KNRM << std::endl;
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalBPrepbTime(time);
}


void Handler::handleLdrPrepareOP(MsgLdrPrepareOPC msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling(C," << this->view << "):" << msg.prettyPrint() << KNRM << std::endl;
  Block      block = msg.block;
  OPproposal prop  = msg.prop;
  OPvote     vote  = msg.vote;
  View v      = prop.getView();
  View vv     = vote.getView();
  bool vm     = verifyLdrPrepareOP(msg);
  if (v >= this->view
      && vv == v
      && !amLeaderOf(v)
      && getLeaderOf(v) == prop.getAuth().getId()
      && vm
      && block.extends(vote.getHash())
      && prop.getHash() == block.hash()) {
    if (v == this->view) {
      respondToLdrPrepareOP(block,prop,OPcert(vote));
    } else {
      // If the message is for later, we store it
      if (DEBUG1) std::cout << KMAG << nfo() << "storing(C):" << msg.prettyPrint() << KNRM << std::endl;
      this->log.storeLdrPrepOp(msg);
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded(C):" << msg.prettyPrint() << KNRM << std::endl;
    if (DEBUG1) std::cout << KMAG << nfo() << "because(C):"
                          << "check-view1="    << std::to_string(v >= this->view)
                          << ";check-view3="   << std::to_string(vv == v) << "(" << vv << "," << v << ")"
                          << ";check-leader1=" << std::to_string(!amLeaderOf(v)) << "(" << v << ")"
                          << ";check-leader2=" << std::to_string(getCurrentLeader() == prop.getAuth().getId())
                          << ";verif-msg="     << std::to_string(vm)
                          << ";check-extends=" << std::to_string(block.extends(vote.getHash()))
                          << ";check-hash="    << std::to_string(prop.getHash() == block.hash())
                          << KNRM << std::endl;
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalBPrepcTime(time);
}


void Handler::handle_ldrprepareopa(MsgLdrPrepareOPA msg, const PeerNet::conn_t &conn) {
  if (DEBUGT) printNowTime(KBLU, "handling MsgLdrPrepareOPA");
  handleLdrPrepareOP(msg);
}


void Handler::handle_ldrprepareopb(MsgLdrPrepareOPB msg, const PeerNet::conn_t &conn) {
  if (DEBUGT) printNowTime(KBLU, "handling MsgLdrPrepareOPB");
  handleLdrPrepareOP(msg);
}


void Handler::handle_ldrprepareopc(MsgLdrPrepareOPC msg, const PeerNet::conn_t &conn) {
  if (DEBUGT) printNowTime(KBLU, "handling MsgLdrPrepareOPC");
  handleLdrPrepareOP(msg);
}


// For leaders to handle votes on their proposals
void Handler::handleBckPrepareOP(MsgBckPrepareOP msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  View v = msg.store.getView();
  if (v == this->view) {
    if (amLeaderOf(v)) {
      //if (DEBUG1) std::cout << KLBLU << nfo() << "storing backup-prepare:" << msg.prettyPrint() << KNRM << std::endl;
      // Beginning of pre-commit phase, we store messages until we get enough of them to start pre-committing
      unsigned int ns = this->log.storeStoreOp(msg.store);
      if (DEBUG1) std::cout << KLBLU << nfo() << "#bck-prepare-op=" << ns << KNRM << std::endl;
      if (ns == this->qsize) {
        if (DEBUG1Y) std::cout << KLBLU << nfo() << "preCommitting(" << this->view << ")" << KNRM << std::endl;
        preCommitOP(msg.store.getView());
        //if (DEBUG1) std::cout << KLBLU << nfo() << "B" << KNRM << std::endl;
      }
      //if (DEBUG1) std::cout << KLBLU << nfo() << "C" << KNRM << std::endl;
    }
  } else {
    //if (DEBUG1) std::cout << KMAG << nfo() << "storing:" << msg.prettyPrint() << KNRM << std::endl;
    if (v > this->view) { log.storeStoreOp(msg.store); }
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalLVoteTime(time);
  if (DEBUG1) std::cout << KLBLU << nfo() << "handled:" << msg.prettyPrint() << KNRM << std::endl;
}


void Handler::handle_bckprepareop(MsgBckPrepareOP msg, const PeerNet::conn_t &conn) {
  handleBckPrepareOP(msg);
}


// Checks that it contains qsize correct signatures
bool Handler::verifyPrepareOP(OPprepare cert) {
  Auths auths = cert.getAuths();
  if (auths.getSize() == this->qsize) {
    std::string s = cert.data();
    bool b = callTEEverifyOP(auths,s);
    if (DEBUG1) std::cout << KLGRN << nfo() << "verify store-cert(" << b << "-" << auths.getSize() << ")" << KNRM << std::endl;
    return b;
  }
  return false;
}


void Handler::executeOP(OPprepare cert) {
  auto endView = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(endView - startView).count();
  startView = endView;
  stats.incExecViews();
  stats.addTotalViewTime(time);
  if (this->transactions.empty()) { this->viewsWithoutNewTrans++; } else { this->viewsWithoutNewTrans = 0; }

  // Execute
  // TODO: We should wait until we received the block corresponding to the hash to execute
  if (DEBUG0 && DEBUGE) std::cout << KRED << nfo() << "OP-EXECUTE(" << this->view << "/" << this->maxViews << ":" << time << ")" << stats.toString() << KNRM << std::endl;

  // Reply
  replyHash(cert.getHash());

  if (timeToStop()) {
    recordStats();
  } else {
    startNewViewOP();
  }
}


void Handler::respondToPreCommitOP(OPprepare cert) {
  // In case we haven't generated a store cert., we generate it now
  unsigned int n = this->log.getOPstores(this->view,1).getAuths().getSize();
  if (DEBUG1) std::cout << KMAG << nfo() << "respondToPreCommitOP:#=" << n << KNRM << std::endl;
  if (n != 1) {
    OPstore store = callTEEstoreOP((this->opprop).prop);
    this->log.storeStoreOp(store);
    if (DEBUG1) std::cout << KMAG << nfo() << "generated store: " << store.prettyPrint() << KNRM << std::endl;
  }

  // and we execute
  if ((this->opprop).prop.getView() == cert.getView()) {
    this->opprop=OPprp((this->opprop).block,(this->opprop).prop,cert);
  }
  this->opprep = cert;

  auto start = std::chrono::steady_clock::now();

  executeOP(cert);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalReplyTime(time);
}


// This is really the decide phase
void Handler::handlePreCommitOP(MsgPreCommitOP msg) {
  auto start = std::chrono::steady_clock::now();

  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  OPprepare cert = msg.cert;
  View v = cert.getView();
  // A pre-commit vote is a combination of f+1 store certificates
  if (v >= this->view && v == cert.getV() && verifyPrepareOP(cert)) {
    if (v == this->view) {
      respondToPreCommitOP(cert);
    } else {
      this->log.storePrepareOp(cert);
    }
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalDecTime(time);
}


void Handler::handle_precommitop(MsgPreCommitOP msg, const PeerNet::conn_t &conn) {
  handlePreCommitOP(msg);
}


bool Handler::validAddOp(View v, OPaccum acc, OPnvblock nv) {
  Block block = nv.block;
  OPstore store = nv.cert.store;
  OPcert cert = nv.cert.cert;

  Hash bhash = block.hash();

  if (store.getView() == v
      && bhash == store.getHash()
      && ((cert.tag == OPCprep && store.getV() == cert.getView() && bhash == cert.getHash()) // this is for a prepare
          || (cert.tag == OPCvote && store.getV() == cert.getView() && block.extends(cert.getHash())) // this is for a vote
          || ((/*cert.tag == OPCacc ||*/ cert.tag == OPCprep)
              && store.getV() == cert.getView() + 1 && block.extends(cert.getHash()))) // this is for an accum or an earlier prepare
      && acc.getView() == v
      && acc.getHash() == store.getHash()
      && acc.getSize() == this->qsize) {
    Auths a1(acc.getAuth());
    Auths a2(store.getAuth());
    Auths a3(cert.getAuths());
    bool bv1 = callTEEverifyOP(a1,acc.data());
    if (bv1) {
      bool bv2 = callTEEverifyOP(a2,store.data());
      if (bv2) {
        bool bv3 = callTEEverifyOP(a3,cert.data());
        if (bv3) { return true; }
        else { if (DEBUG1) std::cout << KBLU << nfo() << "invalidAddOp:verif3" << KNRM << std::endl; }
      } else { if (DEBUG1) std::cout << KBLU << nfo() << "invalidAddOp:verif2" << KNRM << std::endl; }
    } else { if (DEBUG1) std::cout << KBLU << nfo() << "invalidAddOp:verif1" << KNRM << std::endl; }
    return false;
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "invalidAddOp:"
                          << "view1=" << (store.getView() == v) << ";"
                          << "hash1=" << (bhash == store.getHash()) << ";"
                          << "view2a=" << (store.getV() == cert.getView()) << ";"
                          << "hash2a=" << (bhash == cert.getHash()) << ";"
                          << "view2b=" << (store.getV() == cert.getView() + 1) << ";"
                          << "hash2b=" << (block.extends(cert.getHash())) << ";"
                          << "view3=" << (acc.getView() == v) << ";"
                          << "hash3=" << (acc.getHash() == store.getHash()) << ";"
                          << "size="  << (acc.getSize() == this->qsize)
                          << KNRM << std::endl;
    return false;
  }
}


void Handler::handleLdrAddOP(MsgLdrAddOP msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  OPaccum acc = msg.acc;
  OPnvblock nv  = msg.nv;

  View v = acc.getView();
  if (v >= this->view-1) {
    if (validAddOp(v,acc,nv)) {
      if (v == this->view-1) {
        OPvote vote = callTEEvoteOP(acc.getHash());
        PID leader = getCurrentLeader();
        Peers recipients = keep_from_peers(leader);
        sendMsgBckAddOP(vote,recipients);
      } else {
        this->log.storeAccumOp(acc);
        if (DEBUG1) std::cout << KBLU << nfo() << "storing MsgLdrAddOP for later:" << v << "-" << this->view-1 << KNRM << std::endl;
        //if (DEBUG1) std::cout << KRED << nfo() << "TODO" << "(handleLdrAddOP)" << KNRM << std::endl;
        // TODO : store for later
      }
    } else {
      if (DEBUG1) std::cout << KBLU << nfo() << "invalid message:" << msg.prettyPrint() << "-" << this->view-1 << KNRM << std::endl;
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded(view=" << this->view << "):" << msg.prettyPrint() << KNRM << std::endl;
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalLAddTime(time);
}


void Handler::handle_ldraddop(MsgLdrAddOP msg, const PeerNet::conn_t &conn) {
  if (DEBUGT) printNowTime(KBLU, "handling MsgLdrAddOP");
  handleLdrAddOP(msg);
}


bool Handler::validOPvote(OPvote vote) {
  Auths a(vote.getAuths());
  bool b = callTEEverifyOP(a,vote.data());
  if (DEBUG1) std::cout << KBLU << nfo() << "validOPvote=" << b << KNRM << std::endl;
  return b;
}


// For the leader: receive f+1 votes and creates a certificates out of it
void Handler::handleBckAddOP(OPvote vote) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << vote.prettyPrint() << KNRM << std::endl;

  if (vote.getView() >= this->view && validOPvote(vote)) {
    unsigned int m = 0; // the old number of votes
    unsigned int n = this->log.storeVoteOp(vote,&m);
    // TODO: make sure we only do this once!
    if (DEBUG1) std::cout << KBLU << nfo() << "handleBckAddOP:" << m << ":" << n << KNRM << std::endl;
    std::map<View,bool>::iterator it0 = this->prepared.find(this->view);
    if (m < n
        && n == this->qsize
        && vote.getView() == this->view
        // also, we only prepare in the optional phase if we haven't started preparing or if we have started preparing
        // in the optional phase, but not if we have started preparing in the fast phase, i.e., (bool)it0->second == true
        && (it0 == this->prepared.end() || !((bool)it0->second))) {
      OPvote vote = this->log.getOPvote(this->view,this->qsize);
      prepareOpVote(vote);
    }
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalBAddTime(time);
  if (DEBUG1) std::cout << KBLU << nfo() << "handleBckAddOP:done" << KNRM << std::endl;
}


void Handler::handle_bckaddop(MsgBckAddOP msg, const PeerNet::conn_t &conn) {
  if (DEBUGT) printNowTime(KBLU, "handling MsgBckAddOP");
  handleBckAddOP(msg.vote);
}



//---------------------------------------------------------------------------------------------------


/////////////////////////////////////////////////////////
// ---- Chained baseline


// The justification will have a view this->view-1 if things went well,
// and otherwise there will be a gap between just's view and this->view (capturing blank blocks)
JBlock Handler::createNewBlockCh() {
  std::lock_guard<std::mutex> guard(mu_trans);

  if (DEBUG1) std::cout << KBLU << nfo() << "creating new block" << KNRM << std::endl;

  Transaction trans[MAX_NUM_TRANSACTIONS];
  int i = 0;
  // We fill the block we have with transactions we have received so far
  while (i < MAX_NUM_TRANSACTIONS && !this->transactions.empty()) {
    trans[i]=this->transactions.front();
    this->transactions.pop_front();
    i++;
  }

  // std::ofstream d("debug", std::ios_base::app);
  // d << std::to_string(i) << "\n";
  // d.close();

  if (DEBUG1) { std::cout << KGRN << nfo() << "filled block with " << i << " transactions" << KNRM << std::endl; }

  unsigned int size = i;
  // we fill the rest with dummy transactions
  while (i < MAX_NUM_TRANSACTIONS) {
    trans[i]=Transaction();
    i++;
  }
  return JBlock(this->view,this->justNV,size,trans);
}



// TODO: execute also all blocks that come before that haven't been executed yet
void Handler::tryExecuteCh(JBlock block, JBlock block0, JBlock block1) {
  // we skip this step if block0 is the genesis block because it does not have any certificate
  if (block0.getView() != 0) {
    std::vector<JBlock> blocksToExec;
    View view2 = block1.getJust().getCView();
    bool done = false;

    while (!done) {
      if (DEBUG1) std::cout << KBLU << nfo() << "checking whether " << view2 << " can be executed" << KNRM << std::endl;
      // retrive the block corresponding to block0's justification
      std::map<View,JBlock>::iterator it2 = this->jblocks.find(view2);
      if (it2 != this->jblocks.end()) { // if the block is not available, we'll have to handle this later
        JBlock block2 = (JBlock)it2->second;
        if (DEBUG1) std::cout << KBLU << nfo() << "found block at view " << view2 << KNRM << std::endl;

        // We can execute this block if it is not already executed
        if (!block2.isExecuted()) {
          Hash hash1 = block0.getJust().getCHash();
          Hash hash2 = block2.hash();
          // TO FIX
          if (true) { //hash1 == hash2) {
            blocksToExec.insert(blocksToExec.begin(),block2);
            // we see whether we can execute block2's certificate
            if (view2 == 0) { // the genesis block
              done = true;
            } else { block0 = block2; view2 = block2.getJust().getCView(); }
          } else {
            // hashes don't match so we stop because we cannot execute
            if (DEBUG0) std::cout << KBLU << nfo() << "hashes don't match at view " << view2 << ", clearing blocks to execute " << KNRM << std::endl;
            done = true;
            blocksToExec.clear();
          }
        } else {
          // If the block is already executed, we can stop and actually execute all the blocks we have collected so far
          done = true;
        }
      } else {
        // We don't have all the blocks, so we stop because we cannot execute
        if (DEBUG0) std::cout << KBLU << nfo() << "missing block at view " << view2 << ", clearing blocks to execute " << KNRM << std::endl;
        done = true;
        blocksToExec.clear();
      }
    }

    // We execute the blocks we recorded
    for (std::vector<JBlock>::iterator it = blocksToExec.begin(); it != blocksToExec.end(); ++it) {
      JBlock block2 = *it;
      View view2 = block2.getView();

      // We mark the block as being executed
      block2.markExecuted();
      jblocks[view2]=block2;

      auto endView = std::chrono::steady_clock::now();
      double time = std::chrono::duration_cast<std::chrono::microseconds>(endView - startView).count();
      startView = endView;
      stats.incExecViews();
      stats.addTotalViewTime(time);
      this->viewsWithoutNewTrans++;
      stats.endExecTime(view2,endView);
      //if (this->transactions.empty()) { this->viewsWithoutNewTrans++; } else { this->viewsWithoutNewTrans = 0; }

      // Execute
      // TODO: We should wait until we received the block corresponding to the hash to execute
      if (DEBUG0 && DEBUGE) std::cout << KRED << nfo() << "CH-EXECUTE(" << view2 << ";" << this->viewsWithoutNewTrans << ";" << this->view << "/" << this->maxViews << ":" << time << ")" << stats.toString() << KNRM << std::endl;

      // Reply
      replyTransactions(block2.getTransactions());
      if (DEBUG1) std::cout << KBLU << nfo() << "sent replies" << KNRM << std::endl;
    }

    if (timeToStop()) { recordStats(); }
  }
}


// For leaders to check whether they can create a new (this->qsize)-justification
void Handler::checkNewJustCh(RData data) {
  Signs signs = (this->log).getPrepareCh(data.getPropv(),this->qsize);
  // We should not need to check the size of 'signs' as this function should only be called, when this is possible
  if (signs.getSize() == this->qsize) {
    // create the new justification
    this->justNV = Just(data,signs);
    // increment the view
    this->view++;
    // reset the timer
    setTimer();
   // start the new view
    prepareCh();
  }
}



// handle stored MsgLdrPrepareCh messages
void Handler::handleEarlierMessagesCh() {
  if (amCurrentLeader()) {
  } else {
    MsgLdrPrepareCh msg = this->log.firstLdrPrepareCh(this->view);
    if (msg.sign.isSet()  // If we've stored the leader's proposal
        && this->jblocks.find(this->view) == this->jblocks.end()) { // we handle the message if we haven't done so already, i.e., we haven't stored the corresponding block
      if (DEBUG1) std::cout << KMAG << nfo() << "catching up using leader proposal (view=" << this->view << ")" << KNRM << std::endl;
      voteCh(msg.block);
    }
  }
}


void Handler::startNewViewCh() {
  Just justNv = callTEEsignCh();
  // generate justifications until we can generate one for the next view
  while (justNv.getRData().getPropv() < this->view || justNv.getRData().getPhase() != PH1_NEWVIEW) {
    if (DEBUG1) std::cout << KMAG << nfo() << "generaring yet a new-view:" << this->view << ":" << justNv.prettyPrint() << KNRM << std::endl;
    justNv = callTEEsignCh();
  }

  if (justNv.getSigns().getSize() == 1) {

    PID nextLeader = getLeaderOf(this->view+1);
    Peers recipientsNL = keep_from_peers(nextLeader);

    Sign sigNv = justNv.getSigns().get(0);
    MsgNewViewCh msgNv(justNv.getRData(),sigNv);
    // If we're the leader of the next view, we store the message, otherwise we send it
    if (amLeaderOf(this->view+1)) { this->log.storeNvCh(msgNv); }
    else { sendMsgNewViewCh(msgNv,recipientsNL); }

    // increment the view
    this->view++;
    // start the timer
    setTimer();

    if (!amLeaderOf(this->view)) {
      // try to handler earlier messages
      handleEarlierMessagesCh();
    }
  }
}


// Votes for a block, sends the vote, and signs the prepared certif. and sends it
void Handler::voteCh(JBlock block) {
  if (DEBUG1) std::cout << KBLU << nfo() << "voting for " << block.prettyPrint() << KNRM << std::endl;

  this->jblocks[this->view]=block;
  stats.startExecTime(this->view,std::chrono::steady_clock::now());

  View view0 = block.getJust().getCView();
  if (DEBUG1) std::cout << KBLU << nfo() << "retriving block for view " << view0 << KNRM << std::endl;
  // retrive the block corresponding to block's justification
  std::map<View,JBlock>::iterator it0 = this->jblocks.find(view0);
  if (it0 != this->jblocks.end()) { // if the block is not available, we'll have to handle this later
    JBlock block0 = (JBlock)it0->second;
    if (DEBUG1) std::cout << KBLU << nfo() << "block for view " << view0 << " retrieved" << KNRM << std::endl;
    if (DEBUG1) std::cout << KBLU << nfo() << "block is: " << block0.prettyPrint() << KNRM << std::endl;

    View view1 = block0.getJust().getCView();
    if (DEBUG1) std::cout << KBLU << nfo() << "retriving block for view " << view1 << KNRM << std::endl;
    // retrive the block corresponding to block0's justification
    std::map<View,JBlock>::iterator it1 = this->jblocks.find(view1);
    if (it1 != this->jblocks.end()) { // if the block is not available, we'll have to handle this later
      JBlock block1 = (JBlock)it1->second;
      if (DEBUG1) std::cout << KBLU << nfo() << "block for view " << view1 << " retrieved" << KNRM << std::endl;

      Just justPrep = callTEEprepareCh(block,block0,block1);
      Just justNv2 = callTEEsignCh();

      if (DEBUG1) std::cout << KBLU << nfo() << "prepared & signed" << KNRM << std::endl;

      if (justPrep.getSigns().getSize() == 1) {
        Sign sigPrep = justPrep.getSigns().get(0);

        PID nextLeader = getLeaderOf(this->view+1);
        Peers recipientsNL = keep_from_peers(nextLeader);

        // If we're the leader we send a MsgLdrPrepareCh and otherwise we send a MsgPrepareCh
        if (amLeaderOf(this->view)) { // leader of the current view
          MsgLdrPrepareCh msgPrep(block,sigPrep);
          Peers recipientsPrep = remove_from_peers(this->myid);
          sendMsgLdrPrepareCh(msgPrep,recipientsPrep);
        } else { // not the leader of the current view
          MsgPrepareCh msgPrep(justPrep.getRData(),sigPrep);
          // If we're the leader of the next view, we store the message, otherwise we send it
          if (amLeaderOf(this->view+1)) { this->log.storePrepCh(msgPrep); }
          else { sendMsgPrepareCh(msgPrep,recipientsNL); }
        }
        if (DEBUG1) std::cout << KBLU << nfo() << "sent vote" << KNRM << std::endl;

        if (justNv2.getSigns().getSize() == 1) {
          Sign sigNv = justNv2.getSigns().get(0);
          MsgNewViewCh msgNv(justNv2.getRData(),sigNv);
          // If we're the leader of the next view, we store the message, otherwise we send it
          if (amLeaderOf(this->view+1)) { this->log.storeNvCh(msgNv); }
          else { sendMsgNewViewCh(msgNv,recipientsNL); }

          tryExecuteCh(block,block0,block1);

          // The leader of the next view stays in this view until it has received enough votes or timed out
          if (amLeaderOf(this->view+1)) { checkNewJustCh(justPrep.getRData()); }
          else {
            // increment the view
            this->view++;
            // reset the timer
            setTimer();
            // try to handler already received messages
            handleEarlierMessagesCh();
          }
        }
      } else {
        if (DEBUG1) std::cout << KLRED << nfo() << "prepare justification ill-formed:" << justPrep.prettyPrint() << KNRM << std::endl;
      }
    } else {
      if (DEBUG1) std::cout << KLRED << nfo() << "missing block for view " << view1 << KNRM << std::endl;
    }
  } else {
    if (DEBUG1) std::cout << KLRED << nfo() << "missing block for view " << view0 << KNRM << std::endl;
  }
}


// For leader to do begin a view (prepare phase) in Chained version
void Handler::prepareCh() {
  if (DEBUG1) std::cout << KBLU << nfo() << "leader is preparing" << KNRM << std::endl;

  // If we don't have the latest certificate, we have to select one
  if (!this->justNV.isSet() || this->justNV.getRData().getPropv() != this->view-1) {
    // We first create a block that extends the highest prepared block
    this->justNV = this->log.findHighestNvCh(this->view-1);
  }

  JBlock block = createNewBlockCh();
  //this->jblocks[this->view]=block; // Done in voteCh

  voteCh(block);
}


// NEW-VIEW messages are received by leaders
// Once a leader has received 2f+1 new-view messages, it creates a proposal out of the highest prepared block
// and sends this proposal in a PREPARE message
void Handler::handleNewviewCh(MsgNewViewCh msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  Hash   hashP = msg.data.getProph();
  View   viewP = msg.data.getPropv();
  Phase1 ph    = msg.data.getPhase();
  if (hashP.isDummy() && viewP+1 >= this->view && ph == PH1_NEWVIEW && amLeaderOf(viewP+1)) {
    if (viewP+1 == this->view // we're in the correct view
        && this->log.storeNvCh(msg) >= this->qsize // we've stored enough new-view messages to get started
        && this->jblocks.find(this->view) == this->jblocks.end()) { // we haven't prepared yet (i.e., we haven't generated a block for the current view yet)
      prepareCh();
    } else {
      // If the message is for later, we store it
      if (DEBUG1) std::cout << KMAG << nfo() << "storing(view=" << this->view << "):" << msg.prettyPrint() << KNRM << std::endl;
      this->log.storeNvCh(msg);
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded(view=" << this->view << "):" << msg.prettyPrint() << KNRM << std::endl;
    if (DEBUG1) { std::cout << KMAG << nfo()
                            << "test1=" << hashP.isDummy() << ";"
                            << "test2=" << (viewP+1 >= this->view) << "(" << viewP+1 << "," << this->view << ");"
                            << "test3=" << (ph == PH1_NEWVIEW) << ";"
                            << "test4=" << amLeaderOf(viewP+1) << KNRM << std::endl; }
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalNvTime(time);
}


void Handler::handle_newview_ch(MsgNewViewCh msg, const PeerNet::conn_t &conn) {
  handleNewviewCh(msg);
}


// For backups to verify MsgLdrPrepareCh messages send by leaders
Just Handler::ldrPrepareCh2just(MsgLdrPrepareCh msg) {
  JBlock block = msg.block;
  RData rdata(block.hash(),block.getView(),Hash(),View(),PH1_PREPARE);
  Signs signs = Signs(msg.sign);
  return Just(rdata,signs);
}


// Run by the backups in the prepare phase
void Handler::handleLdrPrepareCh(MsgLdrPrepareCh msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling(view=" << this->view << "):" << msg.prettyPrint() << KNRM << std::endl;

  JBlock block = msg.block;
  Sign sign    = msg.sign;
  View v       = block.getView();
  Just just    = ldrPrepareCh2just(msg);

  if (v >= this->view
      && !amLeaderOf(v) // v is the sender
      && Sverify(just.getSigns(),this->myid,this->nodes,just.getRData().toString())) {
    // We first store the ldrPrepare as well as the prepare message corresponding to the ldrPrepare message
    if (amLeaderOf(v+1)) {
      //this->log.storeLdrPrepCh(msg);
      this->log.storePrepCh(MsgPrepareCh(just.getRData(),just.getSigns().get(0)));
    }
    if (v == this->view) {
      voteCh(block);
    } else {
      // If the message is for later, we store it
      if (DEBUG1) std::cout << KMAG << nfo() << "storing(view=" << this->view << "):" << msg.prettyPrint() << KNRM << std::endl;
      this->log.storeLdrPrepCh(msg);
      // We try to handle earlier messages in case we're still stuck earlier
      handleEarlierMessagesCh();
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded:" << msg.prettyPrint() << KNRM << std::endl;
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}


void Handler::handle_ldrprepare_ch(MsgLdrPrepareCh msg, const PeerNet::conn_t &conn) {
  if (DEBUGT) printNowTime(KBLU, "handling MsgLdrPrepareCh");
  handleLdrPrepareCh(msg);
}


// For the leader of view this->view+1 to handle votes
void Handler::handlePrepareCh(MsgPrepareCh msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;

  RData data = msg.data;
  View v = data.getPropv();
  if (v == this->view) {
    if (amLeaderOf(v+1)) {
      // We store messages until we get enough of them to create a new justification
      // We wait to have received the block of the current view to generate a new justification
      //   otherwise we won't be able to preapre our block (we also need the previous block too)
      if (this->log.storePrepCh(msg) >= this->qsize
          && this->jblocks.find(this->view) != this->jblocks.end()) {
        checkNewJustCh(data);
      }
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "storing:" << msg.prettyPrint() << KNRM << std::endl;
    if (v > this->view) { log.storePrepCh(msg); }
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}


void Handler::handle_prepare_ch(MsgPrepareCh msg, const PeerNet::conn_t &conn) {
  handlePrepareCh(msg);
}



/////////////////////////////////////////////////////////
// ---- Chained Cheap&Quick

/////////////////////////////////////////////////////////
// ---- Pacemaker


void Handler::wishToAdvanceOnSync(Sync sync, PID leader) {
  if (this->myid == leader) {
    if (DEBUG1W) std::cout << KBLU << nfo() << "wishToAdvanceOnSync (AM LEADER) "
                           << "sync=" << sync.prettyPrint()
                           << KNRM << std::endl;
    handleSync(sync);
  } else {
    // Records that a sync has been sent
    // TODO: now that syncs are stored, by the time a node becomes leader, it might have too many syncs
    // (see the n == this->qsize check in handleSync)...
    unsigned int n = this->log.storeSync(sync);
    if (DEBUG1W) std::cout << KBLU << nfo() << "number of stored syncs: " << n << KNRM << std::endl;
    Peers recipients = keep_from_peers(leader);
    MsgSync msg = MsgSync(sync);
    sendMsgSync(msg,recipients);
  }

  handleEarlierMessagesSync();
}

// returns the join requests prepared during the current session
Joins Handler::getPreparedJoins(Session s, View v) {
  Joins joins = Joins();

  SView sview = SView(s,v);
  std::map<SView,RBBlock>::iterator it = this->rbblocks.find(sview);
  if (it != this->rbblocks.end()) {
    RBBlock block = (RBBlock)it->second;
    joins.add(block.getJoins());

    bool b = true;
    while (b) {
      std::map<Hash,RBBlock>::iterator it1 = this->rbhblocks.find(block.getPrevHash());
      if (it1 != this->rbhblocks.end()) {
        block = (RBBlock)it1->second;
        if (block.getSession() == s) {
          joins.add(block.getJoins());
        } else { b = false; }
      } else { b = false; }
    }

  }
  return joins;
}

void Handler::wishToAdvance() {
  if (DEBUG1W) std::cout << KBLU << nfo() << "requesting to synchronize" << KNRM << std::endl;

  this->synchronizing = true;
  this->syncAttempts  = 1;

  // We start the timer
  setTimer();

  RBstoreAuth store = this->lastRBstore;
  Sync sync = callTEEsync(store);
  if (!sync.getAuth().getHash().getSet()) {
    if (DEBUG0) std::cout << KRED << nfo() << "FAILED to generate sync:" << sync.prettyPrint()
                          << " - store is:" << store.prettyPrint()
                          << KNRM << std::endl;
    if (DEBUG0) std::cout << KRED << nfo() << "EXIT!(16)" << KNRM << std::endl;
    exit(0);
  }

  Session s = sync.getSession();
  PID leader = getLeaderOf(s);

  Joins joins = getPreparedJoins(store.getStore().getSession(),store.getStore().getView());

  while (joins.in(leader)
         || this->agreedJoins.in(leader)
         || this->receivedJoins.in(leader)) {
    PID newleader = (leader + 1) % this->total;
    if (DEBUG1W) std::cout << KLRED << nfo() << "WISH-TO-ADVANCE - potential leader (" << leader << ")"
                           << " is restarting, moving on to the next one (" << newleader << ")"
                           << KNRM << std::endl;
    leader = newleader;
  }

  if (DEBUG1W) std::cout << KLBLU << nfo() << "sync leader is: " << leader
                        << "; prepared joins: " << joins.prettyPrint()
                        << "; received joins: " << this->receivedJoins.prettyPrint()
                        << KNRM << std::endl;

  wishToAdvanceOnSync(sync,leader);
}

void Handler::wishToJoin() {
  // Assuming that this->session was recovered from disk after restart
  Session s = this->session + 1;
  Join join = callTEEjoinRequest(s);
  Peers recipients = remove_from_peers(this->myid);
  MsgJoin msg = MsgJoin(join);
  sendMsgJoin(msg,recipients);
  this->rejoining = true;
  this->lastJoin  = msg.join;

  // cannot be restarting and the leader
/*  if (this->myid == leader) {
    handleJoinWish(msg);
  }*/
}

// For nodes to handle wishes to join a view
void Handler::handleJoin(MsgJoin msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;

  Session s = msg.join.getSession();
  PID id = msg.join.getAuth().getId();

  if (DEBUG1) std::cout << KBLU << nfo() << "received wish to join from " << id << KNRM << std::endl;

  if (s > this->agreedJoins.get(id).getSession()
      && s > this->receivedJoins.get(id).getSession()
      && s > this->sessions[id]) {

    if (DEBUG1) std::cout << KBLU << nfo() << "new join from " << id << KNRM << std::endl;
    this->receivedJoins.set(msg.join);

    if (getCurrentLeader() == id) {// && !this->synchronizing) {
      if (DEBUG1) std::cout << KLBLU << nfo() << "received join request from leader " << id
                            << " -- triggering a new-view"
                            << KNRM << std::endl;
      startNewViewOrSyncRB(this->lastRBstore);
    }

  } else {

    if (DEBUG1) std::cout << KBLU << nfo() << "old join from " << id
                          << "(session = " << s
                          << "; agreed = " << this->agreedJoins.get(id).getSession()
                          << "; received = " << this->receivedJoins.get(id).getSession()
                          << "; sessions = " << this->sessions[id]
                          << ")"
                          << KNRM << std::endl;

  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

// For leaders to handle "join" request messages
void Handler::handle_join(MsgJoin msg, const PeerNet::conn_t &conn) {
  if (!this->started) {
    this->started=true;
    getStarted();
  }

  //std::lock_guard<std::mutex> guard(mu_handle);
  if (!this->rejoining) {
    handleJoin(msg);
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "rejoining (" << this->lastJoin.prettyPrint() << ")"
                          << " and so not handling:" << msg.prettyPrint()
                          << KNRM << std::endl;
  }
}

Sync Handler::highestSync(std::set<Sync> *syncs) {
  std::set<Sync>::iterator it0=syncs->begin();
  if (DEBUG5) std::cout << KBLU << nfo() << "highest-size1:" << syncs->size() << KNRM << std::endl;
  Sync highest = (Sync)*it0;
  for (std::set<Sync>::iterator it = it0; it!=syncs->end(); ++it) {
    Sync msg = (Sync)*it;
    if (msg.getView() > highest.getView()) { it0 = it; highest = msg; }
  }
  syncs->erase(it0);
  if (DEBUG5) std::cout << KBLU << nfo() << "highest-size2:" << syncs->size() << KNRM << std::endl;
  return highest;
}

// For leaders to handle sync messages
void Handler::handleSync(Sync sync) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1V) std::cout << KBLU << nfo() << "handling:" << sync.prettyPrint() << KNRM << std::endl;

  Session s = sync.getSession();
  View    v = sync.getView();

  if (DEBUG1V) std::cout << KBLU << nfo() << "received sync from " << sync.getAuth().getId() << KNRM << std::endl;

  PID s1 = getLeaderOf(s);
  PID s2 = getLeaderOf(s + this->qsize);

  bool amLeader = false;
  if (s1 <= s2) { amLeader = (s1 <= this->myid && this->myid <= s2); }
  else { amLeader = (s1 <= this->myid || this->myid <= s2); }

  if (s >= this->session + 1 && amLeader) {

    unsigned int n = this->log.storeSync(sync);
    //unsigned int m = this->log.maxSync();

    if (DEBUG1V) std::cout << KBLU << nfo() << "syncs so far=" << n << KNRM << std::endl;

    if (s == this->session + 1 && n == this->qsize) {
      // have now a quorum of sync messages

      std::set<Sync> syncs = this->log.getSync(s);
      Sync highest = highestSync(&syncs);

      RBaccumSyncAuth acc = callTEEaccumSyncRB(highest,syncs);

      // send qc to all other nodes
      MsgSyncTC syncTC = MsgSyncTC(acc,this->myid);
      Peers recipients = remove_from_peers(this->myid);
      sendMsgSyncTC(syncTC,recipients);

      (this->log).storeSyncTC(syncTC);

      Session sa = acc.getAcc().getSession();
      View va = acc.getAcc().getView();
      Joins pastJoins = getPreparedJoins(sa-1,va);
      if (DEBUG5) std::cout << KLMAG << nfo() << "passed joins for "
                            << "(" << sa-1 << "," << va << ")"
                            << ":" << pastJoins.prettyPrint()
                            << KNRM << std::endl;
      INonces nonces = INonces();
      for (int i = 0; i < MAX_NUM_NODES; i++) {
        if (pastJoins.get(i).getNonce().getSet()) {
          INonce nonce = INonce(pastJoins.get(i).getAuth().getId(),pastJoins.get(i).getNonce());
          nonces.set(nonce);
        }
      }
      if (DEBUG1) std::cout << KLMAG << nfo() << "passed nonces:"
                            << nonces.prettyPrint()
                            << KNRM << std::endl;

      // Vote on the TC
      SyncVoteAuth vote = callTEEsyncVote(acc,nonces);
      handleSyncVote(vote);

    }
  } else {

    // TODO: store it if the node is late and should handle this later.
    if (DEBUG1V) std::cout << KMAG << nfo() << "sync message not addressed to the correct node (" << amLeader << ")"
                           << " or with incorrect session number (" << s << "," << this->session << ") :"
                           << sync.prettyPrint() << KNRM << std::endl;

  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

// For leaders to handle "sync" messages
void Handler::handle_sync(MsgSync msg, const PeerNet::conn_t &conn) {
  //std::lock_guard<std::mutex> guard(mu_handle);
  if (!this->rejoining) {
    handleSync(msg.sync);
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "rejoining (" << this->lastJoin.prettyPrint() << ")"
                          << " and so not handling:" << msg.prettyPrint()
                          << KNRM << std::endl;
  }
}

// For backups to handle sync "quorum certificates"
void Handler::handleSyncTC(MsgSyncTC qc) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1V) std::cout << KBLU << nfo() << "handling:" << qc.prettyPrint() << KNRM << std::endl;

  RBaccumSyncAuth acc   = qc.acc;
  PID             Lid   = qc.id; // TO FIX: should be coming from the signature, but not always the case right now
  Session         s     = acc.getAcc().getSession();
  View            v     = acc.getAcc().getView();

  Joins pastJoins = getPreparedJoins(s-1,v);
  if (DEBUG5) std::cout << KLMAG << nfo() << "passed joins for "
                        << "(" << s-1 << "," << v << ")"
                        << ":" << pastJoins.prettyPrint()
                        << KNRM << std::endl;
  INonces nonces = INonces();
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    if (pastJoins.get(i).getNonce().getSet()) {
      INonce nonce = INonce(pastJoins.get(i).getAuth().getId(),pastJoins.get(i).getNonce());
      nonces.set(nonce);
      if (DEBUG5) std::cout << KLMAG << nfo() << "added nonce:"
                            << nonce.prettyPrint()
                            << KNRM << std::endl;
    }
  }
  if (DEBUG5) std::cout << KLMAG << nfo() << "passed nonces:"
                        << nonces.prettyPrint()
                        << KNRM << std::endl;

  PID s1 = getLeaderOf(s);
  PID s2 = getLeaderOf(s + this->qsize);

  bool isLeader = false;
  if (s1 <= s2) { isLeader = (s1 <= Lid && Lid <= s2); }
  else { isLeader = (s1 <= Lid || Lid <= s2); }

  bool amLeader = false;
  if (s1 <= s2) { amLeader = (s1 <= this->myid && this->myid <= s2); }
  else { amLeader = (s1 <= this->myid || this->myid <= s2); }

  if (s >= this->session + 1 && isLeader) {
    if (true) { //hjoins == joins.hash()) {

      // true if the sync-tc is new and needs to be acted upon
      bool bnew = false;

      if ((this->log).newSyncTc(qc)) {
        bnew = true;
        unsigned int n = this->log.storeSyncTC(qc);
        if (amLeader) {
          // The SyncTC message is relayed to the other leaders
          Peers recipients1 = remove_from_peers(this->myid);
          MsgSyncTC msg = MsgSyncTC(acc,this->myid); // TO FIX: should be re-generating an acc?
          if (DEBUG1V) std::cout << KBLU << nfo() << "relaying syncTC as own to all: "
                                 << recipients2string(recipients1)
                                 << KNRM << std::endl;
          sendMsgSyncTC(msg,recipients1);
        } else {
          // The SyncTC message is relayed to the other leaders
          Peers recipients1 = from_to_peers(s1,s2);
          // Need to create a copy of the message otherwise it gets destroyed?
          MsgSyncTC msg = MsgSyncTC(acc,Lid);
          if (DEBUG1V) std::cout << KBLU << nfo() << "relaying syncTC as is to leaders: "
                                 << recipients2string(recipients1)
                                 << KNRM << std::endl;
          sendMsgSyncTC(msg,recipients1);
        }
      } else {
        if (DEBUG1V) std::cout << KBLU << nfo() << "not relaying syncTC because not new" << KNRM << std::endl;
      }

      if (bnew && s == this->session + 1) {
        // Vote on the TC
        SyncVoteAuth vote = callTEEsyncVote(acc,nonces);

        // The vote is sent to the leader that the node got the TC from
        //Peers recipients2 = keep_from_peers(Lid);
        // This leads to unnecessay timeouts if nodes receive TCs from different leaders
        // Instead, send to all leaders:
        Peers recipients2 = from_to_peers(s1,s2);

        if (DEBUG1V) std::cout << KBLU << nfo() << "sending vote on syncTC to: "
                               << recipients2string(recipients2)
                               << KNRM << std::endl;

        sendMsgSyncVote(MsgSyncVote(vote),recipients2);

        if (this->myid == Lid) {
          handleSyncVote(vote);
        }
      } else {
        if (DEBUG1V) std::cout << KBLU << nfo()
                               << "not voting (syncTC's session="
                               << s << ", next session=" << this->session+1 << ")"
                               << KNRM << std::endl;
      }

    } else {
      if (DEBUG1V) std::cout << KBLU << nfo() << "hash in the sync message does not match the joins there" << KNRM << std::endl;
    }
  } else {

    if (DEBUG1V) std::cout << KMAG << nfo() << "sync message not from an expected leader (" << isLeader << ")"
                           << " or with incorrect session number [" << s << "," << this->session << "]:"
                           << qc.prettyPrint() << KNRM << std::endl;

  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

// For backups to handle wish quorum certificates
void Handler::handle_sync_tc(MsgSyncTC msg, const PeerNet::conn_t &conn) {
  //std::lock_guard<std::mutex> guard(mu_handle);
  if (!this->rejoining) {
    handleSyncTC(msg);
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "rejoining (" << this->lastJoin.prettyPrint() << ")"
                          << " and so not handling:" << msg.prettyPrint()
                          << KNRM << std::endl;
  }
}

// For leaders to handle votes to sync
void Handler::handleSyncVote(MsgSyncVote msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1U) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;

  SyncVote vote = msg.vote.getVote();
  PID sender    = msg.vote.getAuth().getId();
  Session  s    = vote.getSession();

  PID s1 = getLeaderOf(s);
  PID s2 = getLeaderOf(s + this->qsize);

  bool b = false;
  if (s1 <= s2) { b = (s1 <= this->myid && this->myid <= s2); }
  else { b = (s1 <= this->myid || this->myid <= s2); }

  if (s >= this->session + 1 && b) {

    unsigned int n = this->log.storeSyncVote(msg.vote);
    if (DEBUG1V) std::cout << KBLU << nfo() << "(sync leader) stored the sync-vote from " << sender
                           << " - has now received " << n << " votes"
                           << KNRM << std::endl;

    if (s == this->session + 1 && n == this->qsize) {
      // have now a quorum of votes

      if (DEBUG1V) std::cout << KBLU << nfo() << "(sync leader) received enough ("
                             << this->qsize
                             << ") votes for a sync-vote-qc"
                             << KNRM << std::endl;

      Auths auths = this->log.getSyncVote(vote,this->qsize); // TODO: get qsize of them only

      SyncVoteAuths votes = SyncVoteAuths(vote,auths);
      MsgSyncVoteQc qc = MsgSyncVoteQc(votes,this->myid);
      Peers recipients = remove_from_peers(this->myid);
      sendMsgSyncVoteQc(qc,recipients);

      handleSyncVoteQc(qc);
    }

  } else {

    if (DEBUG1V) std::cout << KMAG << nfo() << "vote not addressed to the correct node (" << b << ")"
                           << " or with incorrect session number[" << s << "," << this->session << "]:"
                           << msg.prettyPrint()
                           << KNRM << std::endl;

  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

// For leaders to handle "join wish" messages
void Handler::handle_sync_vote(MsgSyncVote msg, const PeerNet::conn_t &conn) {
  //std::lock_guard<std::mutex> guard(mu_handle);
  if (!this->rejoining) {
    handleSyncVote(msg);
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "rejoining (" << this->lastJoin.prettyPrint() << ")"
                          << " and so not handling:" << msg.prettyPrint()
                          << KNRM << std::endl;
  }
}

// For nodes to handle vote qcs
void Handler::handleSyncVoteQc(MsgSyncVoteQc qc) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1U) std::cout << KBLU << nfo() << "handling:" << qc.prettyPrint() << KNRM << std::endl;

  SyncVote vote  = qc.vote.getVote();
  PID      Lid   = qc.id; // TODO: leader id -- should be a signature?
  Session  s     = vote.getSession();
  View     v     = vote.getView();
  INonces  joins = vote.getJoins();

  PID s1 = getLeaderOf(s);
  PID s2 = getLeaderOf(s + this->qsize);

  bool b = false;
  if (s1 <= s2) { b = (s1 <= Lid && Lid <= s2); }
  else { b = (s1 <= Lid || Lid <= s2); }

  if (v > this->lastSync) {

    if ((s == this->session + 1 && b) || this->rejoining) {

      if (DEBUG1U) { std::cout << KLMAG << nfo() << "ending sync - old store certificate: "
                               << this->lastRBstore.prettyPrint()
                               << KNRM << std::endl; }
      RBstoreAuth store = callTEEsyncEnd(qc.vote);
      this->lastRBstore = store;
      this->lastSync    = store.getStore().getView();
      if (DEBUG1U) { std::cout << KLMAG << nfo() << "ended sync - new store certificate: "
                               << this->lastRBstore.prettyPrint()
                               << KNRM << std::endl; }
      if (store.getAuth().getHash().getSet()) {
        if (DEBUG1) { std::cout << KLMAG << nfo() << "syncing:"
                                << " updating session (" << this-> session << "->" << s << ")"
                                << " and view (" << this->view << "->" << v << ")"
                                << KNRM << std::endl; }
        this->session       = s;
        this->view          = v;
        this->rejoining     = false;
        this->synchronizing = false;
        this->syncAttempts  = 0;
        this->agreedJoins.reset();

        std::string joiners = "";

        for (int i = 0; i < MAX_NUM_NODES; i++) {
          if (joins.get(i).getNonce().getSet()) {
            this->sessions[i] = this->session;
            if (this->sessions[i] >= this->receivedJoins.get(i).getSession()) { this->receivedJoins.del(i); }
            if (DEBUG1) { std::cout << KLRED << nfo() << "updated " << i << "'s session: " << this->sessions[i]
                                    << KNRM << std::endl; }
            joiners += std::to_string(joins.get(i).getId()) + ":";
          }
        }

        if (DEBUG0) { std::cout << KRED << nfo() << "synced(s" << s << ",v" << v << "), "
                                << "joiners:" << joiners << KNRM << std::endl; }
        if (DEBUG1) { std::cout << KGRN << nfo() << "now staring a new view" << KNRM << std::endl; }

        startNewViewOrJoinRB(store);

      } else {
        if (DEBUG1) { std::cout << KGRN << nfo() << "couldn't join sync on " << s << KNRM << std::endl; }
      }

    } else {

      if (DEBUG1) std::cout << KMAG << nfo() << "sync QC not from an expected leader (" << b << ")"
                            << " or with incorrect session number [" << s << "," << this->session << "]:"
                            << qc.prettyPrint() << KNRM << std::endl;

      if (s > this->session + 1 && b) {
        unsigned int n = this->log.storeSyncVoteQc(qc);
        if (DEBUG1) std::cout << KMAG << nfo() << "stored the sync-vote-qc message for later (" << n << ")" << KNRM << std::endl;
      }
    }
  } else {

    if (DEBUG1U) std::cout << KMAG << nfo() << "received a sync-vote-qc for view " << v
                           << " but already synchronized at view " << this->lastSync
                           << KNRM << std::endl;

  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

// For backups to handle vote qcs
void Handler::handle_sync_vote_qc(MsgSyncVoteQc msg, const PeerNet::conn_t &conn) {
  //std::lock_guard<std::mutex> guard(mu_handle);
  handleSyncVoteQc(msg);
}

// TODO: allow catching-up with other messages too
// Leaders:
// - check whether f+1 sync messages have been received
// - check whether f+1 sync-vote messages have been received
// Backups:
// - check whether a sync-tc has been received (done)
// - check whether a sync-vote-qc has been received (done)
void Handler::handleEarlierMessagesSync() {
  if (DEBUG1) std::cout << KMAG << nfo() << "trying to handle earlier synchronization messages"
                        << " (leader=" << amCurrentLeader() << ")"
                        << KNRM << std::endl;

  MsgSyncVoteQc msg = (this->log).getSyncVoteQc(this->session + 1);
  if (msg.vote.getAuths().getSize() == this->qsize) {
    if (DEBUG1) std::cout << KMAG << nfo() << "catching up using sync-vote-qc" << KNRM << std::endl;
    handleSyncVoteQc(msg);
  } else {
    std::set<MsgSyncTC> tcs = (this->log).getSyncTcs(this->session + 1);
    if (tcs.size() > 0) {
      MsgSyncTC tc = *next(tcs.begin(),0);
      if (DEBUG1) std::cout << KMAG << nfo() << "catching up using sync-tc" << KNRM << std::endl;
      handleSyncTC(tc);
    } else {
      if (DEBUG1) std::cout << KMAG << nfo() << "no catching up to be done" << KNRM << std::endl;
    }
  }
}


/////////////////////////////////////////////////////////
// ---- Rollback-resilient Damysus


void Handler::handleEarlierMessagesRB() {
  if (DEBUG1) std::cout << KMAG << nfo() << "trying to handle earlier messages"
                        << " (leader=" << amCurrentLeader() << ")"
                        << KNRM << std::endl;

  // *** THIS IS FOR LATE NODES TO PRO-ACTIVELY PROCESS MESSAGES THEY HAVE ALREADY RECEIVED FOR THE NEW VIEW ***
  // We now check whether we already have enough information to start the next view if we're the leader
  if (amCurrentLeader()) {

    prepareRB();

  } else {

    // -----------------
    // received a proposal in a MsgLdrPrepareRB message
    RBproposal prop = (this->log).getPropRB(this->view);
    if (prop.getAcc().getAuth().getHash().getSet()
        && prop.getAcc().getAcc().getSession() == this->session
        && prop.getAcc().getAcc().getView() == this->view
        && this->lastRBvote.getPrepare().getView() < this->view) { // haven't generated own prepare

      if (DEBUG1) std::cout << KMAG << nfo() << "catching up using leader proposal" << KNRM << std::endl;
      respondToLdrPrepareRB(prop.getBlock(),prop.getAcc());

    } else {
      if (DEBUG1) std::cout << KMAG << nfo() << "no catching on leader proposal to be done" << KNRM << std::endl;
    }

    // -----------------
    // received a prepare certificate
    RBprepareAuths preps = (this->log).getPrepareRB(this->view);
    SView sview = SView(this->session,this->view);
    std::map<SView,RBBlock>::iterator it = this->rbblocks.find(sview);
    if (preps.getAuths().getSize() == this->qsize            // received a prepare quorum certificate
        && preps.getPrepare().getSession() == this->session  // for the current session
        && preps.getPrepare().getView() == this->view        // and the current view
        && it != this->rbblocks.end()                        // and holds the block corresponding to that view
                                                             // otherwise: won't be able to store the join requests
        && this->lastRBprep.getPrepare().getView() < this->view) { // haven't handled leader's cert. yet

      if (DEBUG1) std::cout << KMAG << nfo() << "catching up using prepare certificate (RB)" << KNRM << std::endl;
      // TODO: If we're late, we currently store two prepare messages (in the prepare phase,
      // the one from the leader with 1 sig; and in the pre-commit phase, the one with f+1 sigs.
      // We skip the prepare phase (this is otherwise a TEEprepare):
      //callTEEsign();
      // We store the prepare certificate

      respondToLdrPreCommitRB(preps);
      // TODO
      //if (DEBUG1) std::cout << KRED << nfo() << "COULD CATCH UP USING PREPARE CERTIFICATE" << KNRM << std::endl;
      /*
        respondToPrepareFree(msgPrep);
      */
    } else {
      if (DEBUG1) std::cout << KMAG << nfo() << "no catching on leader prepare certificate to be done"
                            << " - check1=" << (preps.getAuths().getSize() == this->qsize)
                            << ";check2="   << (preps.getPrepare().getSession() == this->session)
                            << ";check3="   << (preps.getPrepare().getView() == this->view)
                            << ";check4="   << (it != this->rbblocks.end())
                            << ";check5="   << (this->lastRBprep.getPrepare().getView() < this->view)
                            << KNRM << std::endl;
    }

    // -----------------
    // received a store certificate
    RBstoreAuths pcs = (this->log).getPcRB(this->view);
    if (pcs.getAuths().getSize() == this->qsize
        && this->lastRBexec < this->view) {
      if (DEBUG1) std::cout << KMAG << nfo() << "catching up using pre-commit certificate" << KNRM << std::endl;
/*      if (!(this->lastRBstore.getStore().getView() == this->view)) {
        if (DEBUG1) std::cout << KMAG << nfo() << "ERROR: last store is not for the current view"
                              << " (" << this->view << ")"
                              << KNRM << std::endl;
        if (DEBUG1) std::cout << KMAG << nfo() << "last prep:" << this->lastRBprep.prettyPrint()
                              << KNRM << std::endl;
      }*/
      executeRB(pcs);
    } else {
      if (DEBUG1) std::cout << KMAG << nfo() << "no catching on leader store certificate to be done" << KNRM << std::endl;
    }
  }
}

unsigned int Handler::nextSync() {
  return (this->lastSync + (this->syncPeriod * this->numFaults) + 1);
}

void Handler::startNewViewOrSyncRB(RBstoreAuth store) {
  if (DEBUG1W) std::cout << KBLU << nfo() << "starting a new view or synchronizing"
                         << " (sync attempts=" << this->syncAttempts << ")"
                         << KNRM << std::endl;

  if (this->syncPeriod > 0
      && this->view == nextSync()) {
//      && this->view % (this->syncPeriod * this->numFaults) == 0) {
    // time to synchronize

    if (DEBUG1W) std::cout << KBLU << nfo() << "synchronizing: view=" << this->view << KNRM << std::endl;
    wishToAdvance();

  } else {

    startNewViewOrJoinRB(store);

  }
}


void Handler::startNewViewOrJoinRB(RBstoreAuth store) {
  if (DEBUG1) std::cout << KBLU << nfo() << "starting a new view or joining" << KNRM << std::endl;

  // A node rejoins if:
  // - its id indicates that its a joiner
  // - the current session is a rejoining session
  // - the node is not a leader of the current view -- TODO: get rid of that, and allow timeouts
  if ((this->myid < this->numJoiners)
      && (this->session % this->joinPeriod == 0)) {
//      && !(amLeaderOf(this->view+1))) {
    wishToJoin();
  } else {
    startNewViewRB(store);
  }
}


// For nodes to start a new view
// TODO: also trigger new-views when there is a timeout
void Handler::startNewViewRB(RBstoreAuth store) {
  if (DEBUG1) std::cout << KBLU << nfo() << "starting a new view" << KNRM << std::endl;

  // extracts just one of the stores
  RBnewviewAuth newview = callTEEnewviewRB(store);
  this->view++;

  // TODO: skip the nodes that are known to be restarting
  PID newLeader = getCurrentLeader();

  if (this->agreedJoins.in(newLeader)
      || this->receivedJoins.in(newLeader)) {
    if (DEBUG1W) { std::cout << KLGRN << nfo() << "new consensus leader (" << newLeader << ")"
                            << " is known to be restarting (agreed or just received) and can be skipped"
                            << KNRM << std::endl; }

    return startNewViewOrSyncRB(store);

  } else {
    if (DEBUG1W) { std::cout << KLGRN << nfo() << "new consensus leader (" << newLeader << ")"
                            << " doesn't seem to be restarting"
                            << KNRM << std::endl; }

    // We start the timer
    setTimer();

    if (DEBUG1W) std::cout << KBLU << nfo() << "start-new-view:ok" << KNRM << std::endl;
    MsgNewViewRB msg(newview);
    if (amCurrentLeader()) {
      if (DEBUG1W) std::cout << KBLU << nfo() << "handling new view as leader" << KNRM << std::endl;
      handleEarlierMessagesRB();
      handleNewviewRB(msg);
    }
    else {
      if (DEBUG1W) std::cout << KBLU << nfo() << "handling new view as backup" << KNRM << std::endl;
      PID leader = getCurrentLeader();
      Peers recipients = keep_from_peers(leader);
      sendMsgNewViewRB(msg,recipients);
      handleEarlierMessagesRB();
    }
  }
}

RBnewviewAuth Handler::highestNewViewRB(std::set<RBnewviewAuth> *newviews) {
  std::set<RBnewviewAuth>::iterator it0=newviews->begin();
  if (DEBUG5) std::cout << KBLU << nfo() << "highest-size1:" << newviews->size() << KNRM << std::endl;
  RBnewviewAuth highest = (RBnewviewAuth)*it0;
  for (std::set<RBnewviewAuth>::iterator it = it0; it!=newviews->end(); ++it) {
    RBnewviewAuth msg = (RBnewviewAuth)*it;
    if (msg.getNewview().getPrepv() > highest.getNewview().getPrepv()) { it0 = it; highest = msg; }
  }
  newviews->erase(it0);
  if (DEBUG5) std::cout << KBLU << nfo() << "highest-size2:" << newviews->size() << KNRM << std::endl;
  return highest;
}

RBBlock Handler::createNewRBBlock(Hash hash) {
  if (DEBUG5) std::cout << KBLU << nfo() << "in createNewRBBlock" << KNRM << std::endl;

  auto start = std::chrono::steady_clock::now();

  Transactions trans;
  int i = 0;

  // We fill the block we have with transactions we have received so far
  while (i < MAX_NUM_TRANSACTIONS && !this->transactions.empty()) {
    trans.add(this->transactions.front());
    this->transactions.pop_front();
    i++;
  }

  if (DEBUG1) { std::cout << KGRN << nfo() << "filled block with " << i << " transactions" << KNRM << std::endl; }

  unsigned int size = i;
  // we fill the rest with dummy transactions
  while (i < MAX_NUM_TRANSACTIONS) {
    trans.add(Transaction());
    i++;
  }

  Joins pjoins = getPreparedJoins(this->session,this->view);

  //size = i;
  // Remove from this->receivedJoins the joins of nodes that we know have already joined the sessions requested
  for (int j = 0; j < MAX_NUM_NODES; j++) {
    if (this->sessions[j] >= this->receivedJoins.get(j).getSession()
        || (pjoins.in(j) && pjoins.get(j).getSession() >= this->receivedJoins.get(j).getSession())) {
      this->receivedJoins.del(j);
    }
  }
  unsigned int id = std::stoi(std::to_string(this->myid) + std::to_string(this->view));
  RBBlock b(id,hash,trans,this->session,this->receivedJoins);

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalNewTime(time);

  return b;
}

// For leaders to send prepare certificates to backups at the beginning of the pre-commit phase
// This auth is a backup auth, not the leader's
void Handler::preCommitRB(View view) {
  if (DEBUG1) std::cout << KLBLU << nfo() << "pre-committing:" << view << KNRM << std::endl;

  RBprepareAuths preps = (this->log).getPrepareRB(view);
  // We should not need to check the size of 'signs' as this function should only be called, when this is possible
  if (preps.getAuths().getSize() == this->qsize) {
    this->lastRBprep = preps;
    Peers recipients = remove_from_peers(this->myid);
    sendMsgLdrPreCommitRB(MsgLdrPreCommitRB(preps),recipients);
    if (DEBUG5) std::cout << KLBLU << nfo() << "hash of logged prepare:" << preps.getPrepare().getHash().toString() << KNRM << std::endl;

    // The leader also stores the prepare message
    RBstoreAuth store = callTEEstoreRB(preps);
    this->lastRBstore = store;

    // We store our own commit in the log
    if (this->qsize <= this->log.storePcRB(store)) {
      decideRB(store.getStore());
    }
  }
}

std::string newviews2string(std::set<RBnewviewAuth> newviews) {
  std::string s;
  for (std::set<RBnewviewAuth>::iterator it = newviews.begin(); it != newviews.end(); ++it) {
    s += "|" + ((RBnewviewAuth)(*it)).prettyPrint() + "|";
  }
  return s;
}

// For leaders to begin a view (prepare phase) -- in the RollBack-prevention mode
void Handler::prepareRB() {
  if (DEBUG1) std::cout << KBLU << nfo() << "leader trying to prepare" << KNRM << std::endl;
  std::set<RBnewviewAuth> newviews = this->log.getNewViewRB(this->view,this->qsize);
  if (newviews.size() == this->qsize) {
    // New block
    if (DEBUG5) std::cout << KBLU << nfo() << "highest-sizeA:" << newviews.size() << KNRM << std::endl;
    RBnewviewAuth highest = highestNewViewRB(&newviews);
    if (DEBUG5) std::cout << KBLU << nfo() << "highest-sizeB:" << newviews.size() << KNRM << std::endl;

    if (DEBUG1) std::cout << KBLU << nfo() << "accumulating "
                          << "; highest= " << highest.prettyPrint()
                          << "; newviews= " << newviews2string(newviews)
                          << KNRM << std::endl;
    RBaccumNvAuth acc = callTEEaccumNvRB(highest,newviews);

    // We create a block containing all joins that have been received but not been accepted yet
    RBBlock block = createNewRBBlock(highest.getNewview().getHash());
    Hash Hblock = block.hash();

    RBprepareAuth prep = callTEEprepareRB(Hblock);
    this->lastRBvote = prep;

    SView sview = SView(this->session,this->view);
    this->rbblocks[sview]=block;
    this->rbhblocks[Hblock]=block;

    if (DEBUG1) {
      if (DEBUG1) std::cout << KLBLU << nfo() << "prepared: " << prep.prettyPrint()
                            << KNRM << std::endl;

      Joins pastJoins = getPreparedJoins(this->session,this->view);

      if (DEBUG5) std::cout << KLBLU << nfo() << "passed joins for "
                            << "(" << this->session << "," << this->view << ")"
                            << ":" << pastJoins.prettyPrint()
                            << KNRM << std::endl;
    }

    if (prep.getAuth().getHash().getSet()) {

      auto start = std::chrono::steady_clock::now();

      // This one goes to the backups
      MsgLdrPrepareRB msgLdrPrep(block,prep,acc);
      Peers recipients = remove_from_peers(this->myid);
      sendMsgLdrPrepareRB(msgLdrPrep,recipients);

      auto end = std::chrono::steady_clock::now();
      double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
      stats.addTotalLPrepTime(time);

      if (this->log.storePrepRB(prep) == this->qsize) {
        if (DEBUG1) std::cout << KBLU << nfo() << "stored..." << KNRM << std::endl;
        preCommitRB(prep.getPrepare().getView());
      }
      if (DEBUG1) std::cout << KBLU << nfo() << "prepareRB done" << KNRM << std::endl;
    } else {
      if (DEBUG1) std::cout << KLRED << nfo() << "ERROR: bad prepare certificate: " << prep.prettyPrint() << KNRM << std::endl;
      exit(0);
    }

  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "not enough newviews" << KNRM << std::endl;
  }
}

// Run by the leader
void Handler::handleNewviewRB(MsgNewViewRB msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  Session s = msg.newview.getNewview().getSession();
  View v = msg.newview.getNewview().getView();
  if (v >= this->view && amLeaderOf(v)) {
    if (DEBUG1) std::cout << KBLU << nfo() << "storing new-view from: " << msg.newview.getAuth().getId() << KNRM << std::endl;
    if (!this->started) {
      if (DEBUG1) std::cout << KBLU << nfo() << "getting started from new-view" << KNRM << std::endl;
      this->started=true;
      getStarted();
    }
    unsigned int n = this->log.storeNvRB(msg.newview);
    if (DEBUG1) { std::cout << KBLU << nfo() << "stored new-view from " << msg.newview.getAuth().getId()
                            << " [" << n << "," << this->qsize << "," << v << "," << this->view << "]"
                            << KNRM << std::endl; }
    if (n == this->qsize && v == this->view) {
      if (DEBUG1) std::cout << KBLU << nfo() << "preparing" << KNRM << std::endl;
      prepareRB();
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded[" << v << "," << this->view << "]:" << msg.prettyPrint() << KNRM << std::endl;
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  stats.addTotalNvTime(time);
}


void Handler::handle_newviewRB(MsgNewViewRB msg, const PeerNet::conn_t &conn) {
  std::lock_guard<std::mutex> guard(mu_handle);
  if (!this->rejoining) {
    handleNewviewRB(msg);
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "rejoining (" << this->lastJoin.prettyPrint() << ")"
                          << " and so not handling:" << msg.prettyPrint()
                          << KNRM << std::endl;
  }
}


// For backups to respond to correct MsgLdrPrepareRB messages received from leaders
void Handler::respondToLdrPrepareRB(Hash Hblock, RBaccumNvAuth acc) {
  View view = acc.getAcc().getView();

  RBprepareAuth prep = callTEEprepareRB(Hblock);
  this->lastRBvote = prep;

  PID leader = getCurrentLeader();
  Peers recipients = keep_from_peers(leader);
  sendMsgBckPrepareRB(MsgBckPrepareRB(prep),recipients);
}


// Run by the backups in the prepare phase
void Handler::handleLdrPrepareRB(RBBlock block, RBprepareAuth prep, RBaccumNvAuth acc) {
  if (DEBUGT) printNowTime(KBLU, "handle MsgLdrPrepareRB");
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo()
                        << "handling:" << "LDR-PREPARE-RB[" << block.prettyPrint()
                        << "," << prep.prettyPrint()
                        << "," << acc.prettyPrint()
                        << "]" << KNRM << std::endl;

  if (!this->started) {
    if (DEBUG1) std::cout << KBLU << nfo() << "getting started from ldr-prepare" << KNRM << std::endl;
    this->started=true;
    getStarted();
  }

  Session psession = prep.getPrepare().getSession();
  Session nsession = acc.getAcc().getSession();
  View pview       = prep.getPrepare().getView();
  View nview       = acc.getAcc().getView();
  //View pprepv      = prep.getPrepare().getPrepv();
  View nprepv      = acc.getAcc().getPrepv();
  Hash phblock     = prep.getPrepare().getHash();
  Hash nhblock     = acc.getAcc().getHash();
  //Hash phjoins     = prep.getPrepare().getJHash();
  //Hash nhjoins     = newview.getNewview().getJHash();
  //bool vm     = verifyLdrPrepareFree(acc,block);
  Hash Hblock      = block.hash();

  // HERE

  // We now create an array of join requests that takes into consideration the ones being proposed in the block
  bool bj = true;
  Joins bjoins = block.getJoins();
  // compute the joins from all blocks up to the last prepared one (nprepv)
  Joins pastJoins = getPreparedJoins(psession,nprepv);

  if (DEBUG5) std::cout << KLBLU << nfo() << "passed joins for "
                        << "(" << psession << "," << nprepv << ")"
                        << ":" << pastJoins.prettyPrint()
                        << KNRM << std::endl;

  for (int i = 0; i < MAX_NUM_NODES; i++) {
    if (bjoins.get(i).getNonce().getSet()) {
      if (!(bjoins.get(i).getSession() > pastJoins.get(i).getSession())
          || !(bjoins.get(i).getSession() > this->sessions[i])) {
        if (DEBUG1) std::cout << KLRED << nfo() << "session number in block too low for " << i
                              << ":" << bjoins.get(i).getSession()    // session of join in block
                              << "-" << pastJoins.get(i).getSession() // session in join prepared during current session
                              << "-" << this->sessions[i]             // session locally recorded for i
                              << KNRM << std::endl;
        bj = false;
      }
    }
  }

  if (psession == nsession
      && pview == nview
      && !amLeaderOf(pview)
      && block.extends(nhblock)
      && Hblock == phblock
      && bj) {
    //&& getCurrentLeader() == acc.getAuth().getId()
    //&& vm
    //&& acc.getSize() == this->qsize) {

    SView sview = SView(psession,pview);
    // TODO: we should check the accumulator before storing the block though

    // update the block if it doesn't already exist
    std::map<SView,RBBlock>::iterator it1 = this->rbblocks.find(sview);
    if (it1 == this->rbblocks.end()) {
      this->rbblocks[sview]=block;
    }
    std::map<Hash,RBBlock>::iterator it2 = this->rbhblocks.find(Hblock);
    if (it2 == this->rbhblocks.end()) {
      this->rbhblocks[Hblock]=block;
    }

    if (psession >= this->session
        && pview >= this->view) {

      if (psession == this->session && pview == this->view) {
        respondToLdrPrepareRB(phblock,acc);
      } else {
        // If the message is for later, we store it
        if (DEBUG1) std::cout << KMAG << nfo() << "storing:" << prep.prettyPrint() << KNRM << std::endl;
        RBproposal prop = RBproposal(phblock,acc);
        this->log.storePropRB(prop);
      }

    } else {
      if (DEBUG1) std::cout << KMAG << nfo() << "discarded:" << prep.prettyPrint()
                            << "-- check1=" << (psession >= this->session)
                            << ";check2="   << (pview >= this->view)
                            << KNRM << std::endl;
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "discarded:" << prep.prettyPrint()
                          << " -- check1=" << (psession == nsession)
                          << ";check2="    << (pview == nview)
                          << ";check3="    << (!amLeaderOf(pview))
                          << ";check4="    << (block.extends(nhblock))
                          << ";check5="    << (Hblock == phblock)
                          << ";check6="    << bj
                          << KNRM << std::endl;
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}


void Handler::handle_ldrprepareRB(MsgLdrPrepareRB msg, const PeerNet::conn_t &conn) {
  //std::lock_guard<std::mutex> guard(mu_handle);
  if (DEBUGT) printNowTime(KBLU, "handling MsgLdrPrepareRB");
  if (!this->rejoining) {
    handleLdrPrepareRB(msg.block,msg.prep,msg.acc);
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "rejoining (" << this->lastJoin.prettyPrint() << ")"
                          << " and so not handling:" << msg.prettyPrint()
                          << KNRM << std::endl;
  }
}


// For leaders to handle votes on their proposals (pre-prepare)
void Handler::handleBckPrepareRB(MsgBckPrepareRB msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  Session s = msg.prep.getPrepare().getSession();
  View v = msg.prep.getPrepare().getView();
  if (s == this->session && v == this->view) {
    if (amLeaderOf(v)) {
      if (DEBUG1) std::cout << KLBLU << nfo() << "storing prep" << KNRM << std::endl;
      unsigned int ns = this->log.storePrepRB(msg.prep);
      if (DEBUG5) std::cout << KLBLU << nfo() << "stored prep(" << ns << ")" << KNRM << std::endl;
      if (ns == this->qsize) {
        preCommitRB(msg.prep.getPrepare().getView());
      }
    }
  } else {
    if (s > this->session || v > this->view) {
      log.storePrepRB(msg.prep);
      if (DEBUG1) std::cout << KLBLU << nfo() << "stored prep for later" << KNRM << std::endl;
    }
    else {
      if (DEBUG1) std::cout << KLBLU << nfo() << "discarded prep" << KNRM << std::endl;
    }
  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
  if (DEBUG1) std::cout << KLBLU << nfo() << "handled:" << msg.prettyPrint() << KNRM << std::endl;
}


void Handler::handle_bckprepareRB(MsgBckPrepareRB msg, const PeerNet::conn_t &conn) {
  //std::lock_guard<std::mutex> guard(mu_handle);
  if (!this->rejoining) {
    handleBckPrepareRB(msg);
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "rejoining (" << this->lastJoin.prettyPrint() << ")"
                          << " and so not handling:" << msg.prettyPrint()
                          << KNRM << std::endl;
  }
}

// Logs the joins in the block that has just been "stored"
// -- called right after doing a callTEEtsoreRB
void Handler::acceptJoins() {
  SView sview = SView(this->session,this->view);
  std::map<SView,RBBlock>::iterator it = this->rbblocks.find(sview);
  if (it != this->rbblocks.end()) {
    RBBlock block = (RBBlock)it->second;
    Joins joins = block.getJoins();
    for (int i = 0; i < MAX_NUM_NODES; i++) {
      if (joins.get(i).getNonce().getSet()) {
        // join has now been agreed upon
        if (DEBUG5) std::cout << KLMAG << nfo() << "new agreed upon join: "
                              << joins.get(i).prettyPrint()
                              << KNRM << std::endl;
        if (DEBUG5) std::cout << KLMAG << nfo() << "agreed-before:"
                              << this->agreedJoins.get(i).prettyPrint()
                              << " - all agreed:"
                              << this->agreedJoins.prettyPrint()
                              << KNRM << std::endl;
        this->agreedJoins.set(joins.get(i));
        if (DEBUG5) std::cout << KLMAG << nfo() << "agreed-after:"
                              << this->agreedJoins.get(i).prettyPrint()
                              << " - all agreed:"
                              << this->agreedJoins.prettyPrint()
                              << KNRM << std::endl;
        if (this->receivedJoins.get(i).getNonce().getSet()
            && joins.get(i).getSession() >= this->receivedJoins.get(i).getSession()) {
          this->receivedJoins.del(i);
        }
      }
    }
  } else {
    if (DEBUG1) std::cout << KLRED << nfo() << "cannot accept joins: no block recorded for view " << this->view << KNRM << std::endl;
  }
}

// For backups to respond to MsgLdrPreCommitRB messages receveid from leaders - containing prepare certificates
void Handler::respondToLdrPreCommitRB(RBprepareAuths prep) {
  this->lastRBprep = prep;
  RBstoreAuth store = callTEEstoreRB(prep);
  this->lastRBstore = store;

  MsgBckPreCommitRB msgPc(store);
  Peers recipients = keep_from_peers(getCurrentLeader());
  sendMsgBckPreCommitRB(msgPc,recipients);
  if (DEBUG1) std::cout << KLBLU << nfo() << "sent pre-commit" << KNRM << std::endl;
}

// For backups to handle the prepare certificate sent by the leader
void Handler::handleLdrPreCommitRB(RBprepareAuths cert) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << cert.prettyPrint() << KNRM << std::endl;
  Session s = cert.getPrepare().getSession();
  View    v = cert.getPrepare().getView();
  if (s == this->session && v == this->view) {
    if (!amLeaderOf(this->view)) {
      respondToLdrPreCommitRB(cert);
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "storing:" << cert.prettyPrint() << KNRM << std::endl;
    if (s > this->session || v > this->view) { log.storePrepsRB(cert); }
    if (DEBUG1) std::cout << KMAG << nfo() << "stored prepare certificate!" << KNRM << std::endl;
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

void Handler::handle_ldrprecommitRB(MsgLdrPreCommitRB msg, const PeerNet::conn_t &conn) {
  //std::lock_guard<std::mutex> guard(mu_handle);
  if (!this->rejoining) {
    handleLdrPreCommitRB(msg.cert);
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "rejoining (" << this->lastJoin.prettyPrint() << ")"
                          << " and so not handling:" << msg.prettyPrint()
                          << KNRM << std::endl;
  }
}

void Handler::executeRB(RBstoreAuths store) {
  Time endView = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(endView - startView).count();
  startView = endView;
  if (this->skip < this->view) {
    stats.incExecViews();
    stats.addTotalViewTime(time);
  }
  if (this->transactions.empty()) { this->viewsWithoutNewTrans++; } else { this->viewsWithoutNewTrans = 0; }

  //
  acceptJoins();

  // Execute
  // TODO: We should wait until we received the block corresponding to the hash to execute
  if (DEBUG0 && DEBUGE) std::cout << KRED << nfo() << "RB-EXECUTE(" << this->view << "/" << this->maxViews << ":" << time << ")" << stats.toString() << KNRM << std::endl;
  this->lastRBexec = this->view;

  // Reply
  replyHash(store.getStore().getHash());

  if (timeToStop()) {
    recordStats();
  } else {
    if (this->lastRBstore.getStore().getView() < this->view) {
      if (DEBUG1) std::cout << KMAG << nfo() << "ERROR: last store is not for the current view"
                            << " (" << this->view << ")"
                            << KNRM << std::endl;
      if (DEBUG1) std::cout << KMAG << nfo() << "last store:" << this->lastRBstore.prettyPrint()
                            << KNRM << std::endl;
      if (DEBUG1) std::cout << KMAG << nfo() << "last prep:" << this->lastRBprep.prettyPrint()
                            << KNRM << std::endl;
      if (this->lastRBprep.getPrepare().getView() == this->view) {
        this->lastRBstore = callTEEstoreRB(this->lastRBprep);
        if (DEBUG1) std::cout << KMAG << nfo() << "generated own store:" << this->lastRBstore.prettyPrint()
                              << KNRM << std::endl;
      } else {
        if (DEBUG1) std::cout << KRED << nfo() << "ERROR: last prep is not for the current view"
                              << " (" << this->view << ")"
                              << KNRM << std::endl;
        if (DEBUG0) std::cout << KRED << nfo() << "EXIT!(17)" << KNRM << std::endl;
        exit(0);
      }
    }
/*    RBstoreAuth onestore = RBstoreAuth(store.getStore(),store.getAuths().get(0));
    if (DEBUG1) std::cout << KBLU << nfo() << "current lastRBstore:" << this->lastRBstore.prettyPrint() << KNRM << std::endl;
    if (DEBUG1) std::cout << KBLU << nfo() << "stored:" << onestore.prettyPrint() << KNRM << std::endl;
    this->lastRBstore = onestore;*/
    startNewViewOrSyncRB(this->lastRBstore);
  }
}

// For leaders to send pre-commit (store) certificates to backups at the beginning of the decide phase
void Handler::decideRB(RBstore store) {
  Session s = store.getSession();
  View    v = store.getView();
  RBstoreAuths stores = (this->log).getPcRB(view);
  if (stores.getAuths().getSize() == this->qsize) {
    MsgDecideRB msg(stores);
    Peers recipients = remove_from_peers(this->myid);
    sendMsgDecideRB(msg,recipients);

    executeRB(stores);
  }
}

// For leaders to handle pre-commits from backups (store messages)
void Handler::handleBckPreCommitRB(MsgBckPreCommitRB msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;
  Session s = msg.store.getStore().getSession();
  View    v = msg.store.getStore().getView();

  if (s == this->session & v == this->view) {
    if (amLeaderOf(this->view)) {
      // Beginning of decide phase, we store messages until we get enough of them to start deciding
      if (DEBUG1) std::cout << KBLU << nfo() << "storing pre-commit" << KNRM << std::endl;
      if (this->log.storePcRB(msg.store) == this->qsize) {
        if (DEBUG1) std::cout << KBLU << nfo() << "deciding" << KNRM << std::endl;
        decideRB(msg.store.getStore());
      }
      if (DEBUG5) std::cout << KBLU << nfo() << "stored pre-commit" << KNRM << std::endl;
    }
  } else {
    if (DEBUG1) std::cout << KMAG << nfo() << "storing? " << msg.prettyPrint() << KNRM << std::endl;
    if (s > this->session || v > this->view) {
      log.storePcRB(msg.store);
      if (DEBUG1) std::cout << KMAG << nfo() << "stored pre-commit" << KNRM << std::endl;
    } else {
      if (DEBUG1) std::cout << KMAG << nfo() << "discarded pre-commit" << KNRM << std::endl;
    }
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

void Handler::handle_bckprecommitRB(MsgBckPreCommitRB msg, const PeerNet::conn_t &conn) {
  //std::lock_guard<std::mutex> guard(mu_handle);
  if (!this->rejoining) {
    handleBckPreCommitRB(msg);
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "rejoining (" << this->lastJoin.prettyPrint() << ")"
                          << " and so not handling:" << msg.prettyPrint()
                          << KNRM << std::endl;
  }
}

void Handler::handleDecideRB(MsgDecideRB msg) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << msg.prettyPrint() << KNRM << std::endl;

  Session s = msg.store.getStore().getSession();
  View    v = msg.store.getStore().getView();

  if (s == this->session && v == this->view) {
    if (!(amLeaderOf(this->view))) {
      // Backups execute when receiving a valid store certificate from the leader
      executeRB(msg.store);
    }
  } else {
    if (s > this->session || v > this->view) {
      if (DEBUG1) std::cout << KMAG << nfo() << "storing[" << s << "," << this->session << "," << v << "," << this->view << "]:" << msg.prettyPrint() << KNRM << std::endl;
      log.storePcsRB(msg.store);
      if (DEBUG1) std::cout << KMAG << nfo() << "stored decide!" << KNRM << std::endl;

      // The node is late and should start a new-view
      startNewViewOrSyncRB(this->lastRBstore);
    }
  }
  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

void Handler::handle_decideRB(MsgDecideRB msg, const PeerNet::conn_t &conn) {
  //std::lock_guard<std::mutex> guard(mu_handle);
  if (!this->rejoining) {
    handleDecideRB(msg);
  } else {
    if (DEBUG1) std::cout << KBLU << nfo() << "rejoining (" << this->lastJoin.prettyPrint() << ")"
                          << " and so not handling:" << msg.prettyPrint()
                          << KNRM << std::endl;
  }
}


// ---------------------------------------
// Pacemaker


// TODO: allow catching-up with other messages too
// Leaders:
// - check whether f+1 sync messages have been received
// - check whether f+1 sync-vote messages have been received
// Backups:
// - check whether a sync-tc has been received (done)
// - check whether a sync-vote-qc has been received (done)
void Handler::handleEarlierMessagesPmSync() {
  if (DEBUG1) std::cout << KMAG << nfo() << "trying to handle earlier synchronization messages"
                        << " (leader=" << amCurrentLeader() << ")"
                        << KNRM << std::endl;

  MsgPmSyncVoteQc msg = (this->log).getPmSyncVoteQc(this->view + 1);
  if (msg.vote.getAuths().getSize() == this->qsize) {
    if (DEBUG1) std::cout << KMAG << nfo() << "catching up using sync-vote-qc" << KNRM << std::endl;
    handlePmSyncVoteQc(msg);
  } else {
    std::set<MsgPmSyncTC> tcs = (this->log).getPmSyncTcs(this->view + 1);
    if (tcs.size() > 0) {
      MsgPmSyncTC tc = *next(tcs.begin(),0);
      if (DEBUG1) std::cout << KMAG << nfo() << "catching up using sync-tc" << KNRM << std::endl;
      handlePmSyncTC(tc);
    } else {
      if (DEBUG1) std::cout << KMAG << nfo() << "no catching up to be done" << KNRM << std::endl;
    }
  }
}

void Handler::wishToAdvanceOnPmSync(MsgPmSync msg, PID leader) {
  PmSync sync = msg.sync;

  if (this->myid == leader) {
    handlePmSync(sync);
  } else {
    // Records that a sync has been sent
    // TODO: now that syncs are stored, by the time a node becomes leader, it might have too many syncs
    // (see the n == this->qsize check in handleSync)...
    unsigned int n = this->log.storePmSync(sync);
    if (DEBUG1) std::cout << KBLU << nfo() << "number of stored syncs: " << n << KNRM << std::endl;
    Peers recipients = keep_from_peers(leader);
    MsgPmSync m = MsgPmSync(sync);
    sendMsgPmSync(m,recipients);
  }

  handleEarlierMessagesPmSync();
}

void Handler::wishToAdvancePm() {
  if (DEBUG1) std::cout << KBLU << nfo() << "requesting to synchronize" << KNRM << std::endl;

  this->synchronizing = true;
  this->syncAttempts  = 1;

  // We start the timer
  setTimer();

  FVJust store = this->lastPMstore;
  PmSync sync = callTEEpmSync(store);
  if (!sync.getAuth().getHash().getSet()) {
    if (DEBUG0) std::cout << KRED << nfo() << "FAILED to generate sync:" << sync.prettyPrint()
                          << " - store is:" << store.prettyPrint()
                          << KNRM << std::endl;
    if (DEBUG0) std::cout << KRED << nfo() << "EXIT!(18)" << KNRM << std::endl;
    exit(0);
  }

  MsgPmSync msg = MsgPmSync(sync);
  View v = sync.getView();
  PID leader = getLeaderOf(v);

  if (DEBUG1) std::cout << KLBLU << nfo() << "sync leader is: " << leader
                        << KNRM << std::endl;

  wishToAdvanceOnPmSync(msg,leader);
}

// For nodes to handle vote qcs
void Handler::handlePmSyncVoteQc(MsgPmSyncVoteQc qc) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << qc.prettyPrint() << KNRM << std::endl;

  PmSyncs  vote  = qc.vote;
  PID      Lid   = qc.id; // TODO: leader id -- should be a signature?
  View     v     = vote.getView();

  PID v1 = getLeaderOf(v);
  PID v2 = getLeaderOf(v + this->qsize);

  bool b = false;
  if (v1 <= v2) { b = (v1 <= Lid && Lid <= v2); }
  else { b = (v1 <= Lid || Lid <= v2); }

  if ((v == this->view + 1 && b) || this->rejoining) {

    FVJust store = callTEEpmSyncEnd(vote);
    if (DEBUG1) { std::cout << KLMAG << nfo() << "old store certificate: " << this->lastPMstore.prettyPrint()
                            << KNRM << std::endl; }
    this->lastPMstore = store;
    this->lastSync    = store.getData().getView();
    if (DEBUG1) { std::cout << KLMAG << nfo() << "new store certificate: " << this->lastPMstore.prettyPrint()
                            << KNRM << std::endl; }
    if (store.getAuth1().getHash().getSet()) {
      if (DEBUG1) { std::cout << KLMAG << nfo() << "syncing:"
                              << " updating view (" << this->view << "->" << v << ")"
                              << KNRM << std::endl; }
      this->view          = v;
      this->rejoining     = false;
      this->synchronizing = false;
      this->syncAttempts  = 0;

      if (DEBUG0) { std::cout << KRED << nfo() << "synced(v" << v << ")"
                              << KNRM << std::endl; }
      if (DEBUG1) { std::cout << KGRN << nfo() << "now staring a new view" << KNRM << std::endl; }

      startNewViewOrSyncRB(this->lastRBstore);

    } else {
      if (DEBUG1) { std::cout << KLRED << nfo() << "ERROR: couldn't end sync on " << v << KNRM << std::endl; }
      exit(0);
    }

  } else {

    if (DEBUG1) std::cout << KMAG << nfo() << "sync QC not from an expected leader (" << b << ")"
                          << " or with incorrect view [" << v << "," << this->view << "]:"
                          << qc.prettyPrint() << KNRM << std::endl;

    if (v > this->view + 1 && b) {
      unsigned int n = this->log.storePmSyncVoteQc(qc);
      if (DEBUG1) std::cout << KMAG << nfo() << "stored the sync-vote-qc message for later (" << n << ")" << KNRM << std::endl;
    }

  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

// For leaders to handle votes to sync
void Handler::handlePmSyncVote(PmSync vote) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << vote.prettyPrint() << KNRM << std::endl;

  View   v    = vote.getView();

  PID v1 = getLeaderOf(v);
  PID v2 = getLeaderOf(v + this->qsize);

  bool b = false;
  if (v1 <= v2) { b = (v1 <= this->myid && this->myid <= v2); }
  else { b = (v1 <= this->myid || this->myid <= v2); }

  if (v >= this->view + 1 && b) {

    unsigned int n = this->log.storePmSyncVote(vote);
    if (DEBUG1) std::cout << KBLU << nfo() << "stored the sync-vote - has now received " << n << " votes" << KNRM << std::endl;

    if (v == this->view + 1 && n == this->qsize) {
      // have now a quorum of votes

      Auths auths = this->log.getPmSyncVote(vote,this->qsize); // TODO: get qsize of them only

      PmSyncs votes = PmSyncs(v,vote.getBlock(),auths);
      MsgPmSyncVoteQc qc = MsgPmSyncVoteQc(votes,this->myid);
      Peers recipients = remove_from_peers(this->myid);
      sendMsgPmSyncVoteQc(qc,recipients);

      handlePmSyncVoteQc(qc);
    }

  } else {

    if (DEBUG1) std::cout << KMAG << nfo() << "vote not addressed to the correct node (" << b << ")"
                          << vote.prettyPrint()
                          << KNRM << std::endl;

  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

// For backups to handle sync "quorum certificates"
void Handler::handlePmSyncTC(MsgPmSyncTC qc) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << qc.prettyPrint() << KNRM << std::endl;

  PmSync sync = qc.sync;
  PID    Lid  = qc.id; // TODO: leader id -- should be a signature?
  View   v    = sync.getView();

  PID v1 = getLeaderOf(v);
  PID v2 = getLeaderOf(v + this->qsize);

  bool isLeader = false;
  if (v1 <= v2) { isLeader = (v1 <= Lid && Lid <= v2); }
  else { isLeader = (v1 <= Lid || Lid <= v2); }

  bool amLeader = false;
  if (v1 <= v2) { amLeader = (v1 <= this->myid && this->myid <= v2); }
  else { amLeader = (v1 <= this->myid || this->myid <= v2); }

  if (v >= this->view + 1 && isLeader) {

    // true if the sync-tc is new and needs to be acted upon
    bool bnew = false;

    if ((this->log).newPmSyncTc(qc)) {
      bnew = true;
      unsigned int n = this->log.storePmSyncTC(qc);
      if (amLeader) {
        if (DEBUG1) std::cout << KBLU << nfo() << "relaying syncTC as own to all" << KNRM << std::endl;
        // The SyncTC message is relayed to the other leaders
        Peers recipients1 = remove_from_peers(this->myid);
        MsgPmSyncTC msg = MsgPmSyncTC(sync,this->myid);
        sendMsgPmSyncTC(msg,recipients1);
      } else {
        if (DEBUG1) std::cout << KBLU << nfo() << "relaying syncTC as is to leaders" << KNRM << std::endl;
        // The SyncTC message is relayed to the other leaders
        Peers recipients1 = from_to_peers(v1,v2);
        // Need to create a copy of the message otherwise it gets destroyed?
        MsgPmSyncTC msg = MsgPmSyncTC(sync,Lid);
        sendMsgPmSyncTC(msg,recipients1);
      }
    } else {
      if (DEBUG1) std::cout << KBLU << nfo() << "not relaying syncTC because not new" << KNRM << std::endl;
    }

    if (bnew && v == this->view + 1) {
      // Vote on the TC
      PmSync vote = callTEEpmSyncVote(sync);

      // The vote is sent to the leader that the node got the TC from
      Peers recipients2 = keep_from_peers(Lid);
      sendMsgPmSyncVote(MsgPmSyncVote(vote),recipients2);

      if (this->myid == Lid) {
        handlePmSyncVote(vote);
      }
    }
  } else {

    if (DEBUG1) std::cout << KMAG << nfo() << "sync message not from an expected leader (" << isLeader << ")"
                          << " or with incorrect session view [" << v << "," << this->view << "]:"
                          << qc.prettyPrint() << KNRM << std::endl;

  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

// For leaders to handle sync messages
void Handler::handlePmSync(PmSync sync) {
  auto start = std::chrono::steady_clock::now();
  if (DEBUG1) std::cout << KBLU << nfo() << "handling:" << sync.prettyPrint() << KNRM << std::endl;

  View v = sync.getView();

  if (DEBUG1) std::cout << KBLU << nfo() << "received sync from " << sync.getAuth().getId() << KNRM << std::endl;

  PID v1 = getLeaderOf(v);
  PID v2 = getLeaderOf(v + this->qsize);

  bool amLeader = false;
  if (v1 <= v2) { amLeader = (v1 <= this->myid && this->myid <= v2); }
  else { amLeader = (v1 <= this->myid || this->myid <= v2); }

  if (v >= this->view + 1 && amLeader) {

    unsigned int n = this->log.storePmSync(sync);
    //unsigned int m = this->log.maxSync();

    if (n == this->qsize) {
      // have now a quorum of sync messages

      std::set<PmSync> syncs = this->log.getPmSync(v);

      // select the sync with the highest view
      int k = 0;
      PmSync highest = PmSync();
      for (std::set<PmSync>::iterator it=syncs.begin(); it!=syncs.end(); ++it) {
        PmSync someSync = (PmSync)*it;
        View i = someSync.getView();
        if (i >= k) { highest = someSync; }
      }

      // send qc to all other nodes
      MsgPmSyncTC syncTC = MsgPmSyncTC(highest,this->myid);
      Peers recipients = remove_from_peers(this->myid);
      sendMsgPmSyncTC(syncTC,recipients);

      (this->log).storePmSyncTC(syncTC);

      // Vote on the TC
      PmSync vote = callTEEpmSyncVote(sync);
      handlePmSyncVote(vote);

    }
  } else {

    // TODO: store it if the node is late and should handle this later.
    if (DEBUG1) std::cout << KMAG << nfo() << "sync message not addressed to the correct node (" << amLeader << ")"
                          << sync.prettyPrint() << KNRM << std::endl;

  }

  auto end = std::chrono::steady_clock::now();
  double time = std::chrono::duration_cast<std::chrono::microseconds>(end - start).count();
  stats.addTotalHandleTime(time);
}

void Handler::handle_pm_sync(MsgPmSync msg, const PeerNet::conn_t &conn) {
  //std::lock_guard<std::mutex> guard(mu_handle);
  handlePmSync(msg.sync);
}

void Handler::handle_pm_sync_tc(MsgPmSyncTC msg, const PeerNet::conn_t &conn) {
  handlePmSyncTC(msg);
}

void Handler::handle_pm_sync_vote(MsgPmSyncVote msg, const PeerNet::conn_t &conn) {
  handlePmSyncVote(msg.vote);
}

void Handler::handle_pm_sync_vote_qc(MsgPmSyncVoteQc msg, const PeerNet::conn_t &conn) {
  handlePmSyncVoteQc(msg);
}
