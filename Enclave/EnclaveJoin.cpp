#include "EnclaveShare.h"

// To use sgx_read_rand:
#include <sgx_trts.h>

PID jid;                   // TODO: remove as it should come from another file
unsigned int jsession = 0; // TODO: remove as it should come from another file
unsigned int jview    = 0; // TODO: remove as it should come from another file
unsigned int jprepv   = 0; // TODO: remove as it should come from another file
unsigned int lastvote = 0;

hash_t nonce = noHash();

bool synchronizing = false;
bool jprepared     = false;
bool jfirst        = true;

View jviews[MAX_NUM_NODES];

const char jsecret[] = {
  "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgnI0T6AoPs+ufh54e\n"
  "3tr6ywY7KkMBZhBs69NvMpvtXeehRANCAAS+G04ABpuwCvaS0v5fi9vuNOEitPon\n"
  "4nIDK/IJOsGXv85Jw5wayZI19lSB6ox05rLB+CxmEXrDyiOhX8Sz7c0L\n"
};

hash_t jHash(std::string text) {
  hash_t hash;
  if (!SHA256 ((const unsigned char *)text.c_str(), text.size(), hash.hash)) { }
  hash.set = true;
  return hash;
}

auth_t jAuthenticate(std::string text) {
  auth_t auth;
  std::string s = std::to_string(jid) + jsecret + text;
  auth.id   = jid;
  auth.hash = jHash(s);
  return auth;
}

bool jVerify(std::string text, auth_t a) {
  unsigned char hash[SHA256_DIGEST_LENGTH];
  std::string s = std::to_string(a.id) + jsecret + text;
  if (!SHA256 ((const unsigned char *)s.c_str(), s.size(), hash)) { }
  return eq_hashes(a.hash.hash,hash);
}

bool jVerifyAuths(std::string text, auths_t auths) {
  for (int i = 0; i < auths.size; i++) {
    if (!jVerify(text,auths.auths[i])) {
      ocall_print(("ENCLAVE:NOT OK " + std::to_string(auths.auths[i].id) + ":" + std::to_string(jid)).c_str());
      return false;
    }
    else {
      //ocall_print(("ENCLAVE:OK " + std::to_string(auths.auths[i].id) + ":" + std::to_string(jid)).c_str());
    }
  }
  return true;
}

sgx_status_t TEEinitializeRB(PID *me, rbstore_auth_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  jid = *me;
  ocall_print(("ENCLAVE:set up id-" + std::to_string(jid)).c_str());

  // TODO: not quite right
  nonce = newHash();

  res->store.session = jsession;
  res->store.view    = jview;
  res->store.hash    = newHash();

  std::string s =
    std::to_string(res->store.session)
    + std::to_string(res->store.view)
    + hash2string(res->store.hash);

  res->auth = jAuthenticate(s);

  return status;
}

sgx_status_t TEEsync(rbstore_auth_t *store, sync_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  if (nonce.set == true && store->store.session == jsession && store->store.view == jprepv) {

    synchronizing = true;

    res->session = store->store.session + 1;
    res->view    = store->store.view;
    res->hash    = store->store.hash;

    std::string s = (std::to_string(res->session)
                     + std::to_string(res->view)
                     + hash2string(res->hash));
    res->auth = jAuthenticate(s);

  } else {
    ocall_print(("TEEsync error - nonce.set=" + std::to_string(nonce.set)
                 + ";store.session=" + std::to_string(store->store.session)
                 + ";jsession=" + std::to_string(jsession)
                 + ";store.view=" + std::to_string(store->store.view)
                 + ";jprepv=" + std::to_string(jprepv)).c_str());
  }

  return status;
}

sgx_status_t TEEjoinRequest(Session *s, join_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  if (nonce.set == false) {
    uint32_t val;
    sgx_read_rand((unsigned char *) &val, 4);

    std::string s = std::to_string(val);
    if (!SHA256 ((const unsigned char *)s.c_str(), s.size(), nonce.hash)) { }
    nonce.set = true;
  }

  res->session = *s;
  res->nonce = nonce;
  std::string str = std::to_string(res->session) + hash2string(res->nonce);
  res->auth = jAuthenticate(str);

  return status;
}

sgx_status_t TEEsyncVote(rbaccum_sync_auth_t *acc, inonces_t *nonces, sync_vote_auth_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  if (acc->acc.session == jsession + 1
      && acc->acc.view >= jprepv) {

    res->vote.session = acc->acc.session;
    res->vote.view    = acc->acc.view;
    res->vote.hash    = acc->acc.hash;

    std::string s =
      (std::to_string(res->vote.session)
       + std::to_string(res->vote.view)
       + hash2string(res->vote.hash));

    for (int i = 0; i < MAX_NUM_NODES; i++) {
      res->vote.joins.inonces[i].id    = nonces->inonces[i].id;
      res->vote.joins.inonces[i].nonce = nonces->inonces[i].nonce;

      s += std::to_string(res->vote.joins.inonces[i].id);
      s += hash2string(res->vote.joins.inonces[i].nonce);
    }

    res->auth = jAuthenticate(s);
  }

  return status;
}

sgx_status_t TEEspSyncVote(rbaccum_sync_auth_t *acc, sp_sync_vote_auth_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  if (acc->acc.session == jsession + 1
      && acc->acc.view >= jprepv) {

    res->vote.session = acc->acc.session;
    res->vote.view    = acc->acc.view;
    res->vote.hash    = acc->acc.hash;

    std::string s =
      (std::to_string(res->vote.session)
       + std::to_string(res->vote.view)
       + hash2string(res->vote.hash));

    res->auth = jAuthenticate(s);
  }

  return status;
}

void mkNewStore(Session session, View view, hash_t hash, rbstore_auth_t *res) {
  jsession      = session;
  jview         = view;
  jprepv        = view;
  synchronizing = false;

  res->store.session = session;
  res->store.view    = view;
  res->store.hash    = hash;

  std::string s =
    std::to_string(res->store.session)
    + std::to_string(res->store.view)
    + hash2string(res->store.hash);

  res->auth = jAuthenticate(s);
}

sgx_status_t TEEsyncEnd(sync_vote_auths_t *qc, rbstore_auth_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  sync_vote_t vote  = qc->vote;
  inonces_t   joins = vote.joins;

  std::string s = std::to_string(vote.session) + std::to_string(vote.view) + hash2string(vote.hash);
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    s += std::to_string(joins.inonces[i].id) + hash2string(joins.inonces[i].nonce);
  }
  if (jVerifyAuths(s,qc->auths)) {
    bool c1 = (vote.session > jsession
               && joins.inonces[jid].nonce.set == true
               && eqHashes(joins.inonces[jid].nonce,nonce));
    bool c2 = (vote.session == jsession + 1 && joins.inonces[jid].nonce.set == false);
    if (c1 || c2) {
      mkNewStore(vote.session,vote.view,vote.hash,res);
    } else {
      ocall_print(("ENCLAVE:bools false:" + std::to_string(c1) + ":" + std::to_string(c2) + ":" + std::to_string(jid)).c_str());
      res->auth.hash.set = false;
    }
  } else {
    ocall_print(("ENCLAVE:couldn't verify:" + std::to_string(jid)).c_str());
    res->auth.hash.set = false;
  }

  return status;
}

sgx_status_t TEEspSyncEnd(sp_sync_vote_auths_t *qc, rbstore_auth_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  sp_sync_vote_t vote = qc->vote;

  std::string s = std::to_string(vote.session) + std::to_string(vote.view) + hash2string(vote.hash);
  if (jVerifyAuths(s,qc->auths)) {
    bool c2 = (vote.session == jsession + 1);
    if (c2) {
      mkNewStore(vote.session,vote.view,vote.hash,res);
    } else {
      ocall_print(("ENCLAVE:bools false(sp):" + std::to_string(jid)).c_str());
      res->auth.hash.set = false;
    }
  } else {
    ocall_print(("ENCLAVE:couldn't verify(sp):" + std::to_string(jid)).c_str());
    res->auth.hash.set = false;
  }

  return status;
}

// TODO: verify the signature too:
sgx_status_t TEEprepareRB(hash_t *hblock, rbprepare_auth_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  if (!jprepared) {

    jprepared = true;

    res->prep.session = jsession;
    res->prep.view    = jview;
    res->prep.hash    = *hblock;

    std::string s =
      std::to_string(res->prep.session)
      + std::to_string(res->prep.view)
      + hash2string(res->prep.hash);

    res->auth = jAuthenticate(s);
  }

  return status;
}

// TODO: verify the signatures too:
sgx_status_t TEEstoreRB(rbprepare_auths_t *prep, rbstore_auth_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  if (prep->prep.session == jsession
      && prep->prep.view == jview
      && synchronizing == false) {

    jprepv = prep->prep.view;

    //ocall_print(("TEEstoreRB: jprepv=" + std::to_string(jprepv)).c_str());

    res->store.session = jsession;
    res->store.view    = jview;
    res->store.hash    = prep->prep.hash;

    std::string s =
      std::to_string(res->store.session)
      + std::to_string(res->store.view)
      + hash2string(res->store.hash);

    res->auth = jAuthenticate(s);
  }

  return status;
}

// TODO: verify the signature too
sgx_status_t TEEnewviewRB(rbstore_auth_t *store, rbnewview_auth_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  hash_t hblock = store->store.hash;

/*
  // Initial view
  if (jsession == 0 && jprepv == 0) {
    hblock = newHash();
    hjoins = newHash();
  }
*/

  if (store->store.session == jsession
      && store->store.view == jprepv) {

    jview++;
    jprepared = false;

    res->newview.session = jsession;
    res->newview.view    = jview;
    res->newview.prepv   = jprepv;
    res->newview.hash    = hblock;

    std::string s =
      std::to_string(res->newview.session)
      + std::to_string(res->newview.view)
      + std::to_string(res->newview.prepv)
      + hash2string(res->newview.hash);

    res->auth = jAuthenticate(s);
  }

  return status;
}

// TODO: verify the signature too
sgx_status_t TEEaccumNvRB(rbnewview_auth_t *j, rbnewviews_t *js, rbaccum_nv_auth_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  bool b = true;

  for (int i = 0; i < MAX_NUM_SIGNATURES-1; i++) {
    if ((js->newviews[i].newview.session != j->newview.session)
        || (js->newviews[i].newview.view != j->newview.view)
        || (js->newviews[i].newview.prepv > j->newview.prepv)) { b = false; }
  }

  if (b) {
    res->acc.session = j->newview.session;
    res->acc.view    = j->newview.view;
    res->acc.prepv   = j->newview.prepv;
    res->acc.hash    = j->newview.hash;

    std::string s =
      std::to_string(res->acc.session)
      + std::to_string(res->acc.view)
      + std::to_string(res->acc.prepv)
      + hash2string(res->acc.hash);

    res->auth = jAuthenticate(s);
  } else {
    ocall_print(("ENCLAVE[" + std::to_string(jid) + "]:couldn't accumulate").c_str());
    res->auth.hash.set = false;
  }

  return status;
}

// TODO: verify the signature too
sgx_status_t TEEaccumSyncRB(sync_t *j, syncs_t *js, rbaccum_sync_auth_t *res) {
  sgx_status_t status = SGX_SUCCESS;

  bool b = true;

  for (int i = 0; i < MAX_NUM_SIGNATURES-1; i++) {
    if ((js->syncs[i].session != j->session)
        || (js->syncs[i].view > j->view)) { b = false; }
  }

  if (b) {
    res->acc.session = j->session;
    res->acc.view    = j->view;
    res->acc.hash    = j->hash;

    std::string s =
      std::to_string(res->acc.session)
      + std::to_string(res->acc.view)
      + hash2string(res->acc.hash);

    res->auth = jAuthenticate(s);
  }

  return status;
}
