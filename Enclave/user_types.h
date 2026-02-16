#ifndef USER_TYPES_H
#define USER_TYPES_H


//#include <array>

#include <stdbool.h>

// Interface to the Enclave

#include <openssl/sha.h>
#include "../App/types.h"
#include "../App/config.h"
#include "../App/key.h"


typedef struct _pids_t
{
  unsigned int num_nodes;
  PID pids[MAX_NUM_NODES];
} pids_t;

typedef struct _hash_t
{
  unsigned char hash[SHA256_DIGEST_LENGTH];
  //std::array<unsigned char,SHA256_DIGEST_LENGTH> hash;
  bool set;
} hash_t;

typedef struct _rdata_t
{
  hash_t proph;
  View   propv;
  hash_t justh;
  View   justv;
  Phase1 phase;
} rdata_t;

typedef struct _fdata_t
{
  hash_t justh;
  View   justv;
  View   view;
} fdata_t;

typedef struct _auth_t
{
  PID    id;
  hash_t hash;
} auth_t;

typedef struct _auths_t
{
  unsigned int size;
  auth_t auths[MAX_NUM_SIGNATURES];
} auths_t;

typedef struct _payload_t
{
  unsigned int size;
  unsigned char data[MAX_SIZE_PAYLOAD];
} payload_t;

typedef struct _sign_t
{
  bool set;
  PID signer;
  unsigned char sign[SIGN_LEN];
} sign_t;

typedef struct _signs_t
{
  unsigned int size;
  sign_t signs[MAX_NUM_SIGNATURES];
} signs_t;

typedef struct _just_t
{
  bool set;
  rdata_t rdata;
  signs_t signs;
} just_t;

typedef struct _fjust_t
{
  bool set;
  fdata_t data;
  auth_t auth;
} fjust_t;

typedef struct _ofjust_t
{
  bool set;
  fdata_t data;
  auths_t auths;
} ofjust_t;

typedef struct _fvjust_t
{
  bool set;
  fdata_t data;
  auth_t auth1;
  auth_t auth2;
} fvjust_t;

typedef struct _pjust_t
{
  hash_t hash;
  View view;
  auth_t auth;
  auths_t auths;
} pjust_t;

typedef struct _hjust_t
{
  bool set;
  hash_t hash;
  View view;
  auth_t auth;
} hjust_t;

typedef struct _onejust_t
{
  bool set;
  rdata_t rdata;
  sign_t sign;
} onejust_t;

typedef struct _onejusts_t
{
  onejust_t justs[MAX_NUM_SIGNATURES];
} onejusts_t;

typedef struct _fjusts_t
{
  fjust_t justs[MAX_NUM_SIGNATURES-1];
} fjusts_t;

typedef struct _cert_t
{
  View view;
  hash_t hash;
  signs_t signs;
} cert_t;

typedef struct _cdata_t
{
  Phase1 phase;
  View view;
  cert_t cert;
} cdata_t;

typedef struct _vote_t
{
  cdata_t cdata;
  sign_t sign;
} vote_t;

typedef struct _votes_t
{
  vote_t votes[MAX_NUM_SIGNATURES];
} votes_t;

typedef struct _accum_t
{
  bool set;
  View view;
  View prepv;
  hash_t hash;
  unsigned int size;
  sign_t sign;
} accum_t;

typedef struct _haccum_t
{
  bool set;
  View view;
  hash_t hash;
  unsigned int size;
  auth_t auth;
  auth_t authp; // authenticator of the proposal
} haccum_t;

typedef struct _trans_t
{
  CID clientid;
  TID transid;
  unsigned char data[PAYLOAD_SIZE];
} trans_t;

typedef struct _jblock_t
{
  bool set;
  bool executed;
  View view;
  just_t just;
  unsigned int size;
  trans_t trans[MAX_NUM_TRANSACTIONS];
} jblock_t;

typedef struct _ca_t
{
  CAtag tag;
  union{ cert_t cert; accum_t accum; };
} ca_t;

typedef struct _cblock_t
{
  bool set;
  bool executed;
  View view;
  ca_t cert;
  unsigned int size;
  trans_t trans[MAX_NUM_TRANSACTIONS];
} cblock_t;


// "uniform" vote
typedef struct _uvote_t
{
  cdata_t cdata;
  signs_t signs;
} uvote_t;

typedef struct _opstore_t
{
  View view;
  hash_t hash;
  View v;
  auth_t auth;
} opstore_t;

typedef struct _opstores_t
{
  opstore_t stores[MAX_NUM_SIGNATURES-1];
} opstores_t;

typedef struct _opprepare_t
{
  View view;
  hash_t hash;
  View v;
  auths_t auths;
} opprepare_t;

typedef struct _opproposal_t
{
  hash_t hash;
  View view;
  auth_t auth;
} opproposal_t;

typedef struct _opvote_t
{
  hash_t hash;
  View view;
  auths_t auths;
} opvote_t;

typedef struct _opaccum_t
{
  bool set;
  NVkind kind;
  View view;
  hash_t hash;
  unsigned int size;
  auth_t auth;
} opaccum_t;

typedef struct _sync_t
{
  Session session;
  View    view;
  hash_t  hash;
  auth_t  auth;
} sync_t;

typedef struct _syncs_t
{
  sync_t syncs[MAX_NUM_SIGNATURES-1];
} syncs_t;

typedef struct _join_t
{
  Session session;
  hash_t nonce;
  auth_t auth;
} join_t;

typedef struct _joins_t
{
  join_t joins[MAX_NUM_NODES];
} joins_t;

typedef struct _views_t
{
  View views[MAX_NUM_NODES];
} views_t;

/*
typedef struct _join_wish_qc_t
{
  View view;
  unsigned int size;
  join_wish_t wishes[MAX_NUM_SIGNATURES];
} join_wish_qc_t;
*/

/*
typedef struct _vjoins_t
{
  View from;
  View to;
  joins_t joins;
  views_t views;
} vjoins_t;
*/

typedef struct _inonce_t
{
  PID    id;
  hash_t nonce;
} inonce_t;

typedef struct _inonces_t
{
  inonce_t inonces[MAX_NUM_NODES];
} inonces_t;

typedef struct _sync_vote_t
{
  Session   session;
  View      view;
  hash_t    hash;
  inonces_t joins;
} sync_vote_t;

// "simple" sync vote, i.e., without nonces
typedef struct _sp_sync_vote_t
{
  Session   session;
  View      view;
  hash_t    hash;
} sp_sync_vote_t;

typedef struct _sync_vote_auth_t
{
  sync_vote_t vote;
  auth_t      auth;
} sync_vote_auth_t;

// "simple" sync vote, i.e., without nonces
typedef struct _sp_sync_vote_auth_t
{
  sp_sync_vote_t vote;
  auth_t         auth;
} sp_sync_vote_auth_t;

typedef struct _sync_vote_auths_t
{
  sync_vote_t vote;
  auths_t     auths;
} sync_vote_auths_t;

// "simple" sync vote, i.e., without nonces
typedef struct _sp_sync_vote_auths_t
{
  sp_sync_vote_t vote;
  auths_t        auths;
} sp_sync_vote_auths_t;

/*
typedef struct _join_vote_qc_t
{
  vjoins_t vjoins;
  auths_t auths;
} join_vote_qc_t;
*/

typedef struct _rbprepare_t
{
  Session session;
  View    view;
  hash_t  hash;
} rbprepare_t;

typedef struct _rbprepare_auth_t
{
  rbprepare_t prep;
  auth_t      auth;
} rbprepare_auth_t;

typedef struct _rbprepare_auths_t
{
  rbprepare_t prep;
  auths_t     auths;
} rbprepare_auths_t;

typedef struct _rbaccum_nv_t
{
  Session session;
  View    view;
  View    prepv;
  hash_t  hash;
} rbaccum_nv_t;

typedef struct _rbaccum_nv_auth_t
{
  rbaccum_nv_t acc;
  auth_t      auth;
} rbaccum_nv_auth_t;

typedef struct _rbaccum_sync_t
{
  Session session;
  View    view;
  hash_t  hash;
} rbaccum_sync_t;

typedef struct _rbaccum_sync_auth_t
{
  rbaccum_sync_t acc;
  auth_t         auth;
} rbaccum_sync_auth_t;

typedef struct _rbnewview_t
{
  Session session;
  View    view;
  View    prepv;
  hash_t  hash;
} rbnewview_t;

typedef struct _rbnewview_auth_t
{
  rbnewview_t newview;
  auth_t      auth;
} rbnewview_auth_t;

typedef struct _rbnewviews_t
{
  rbnewview_auth_t newviews[MAX_NUM_SIGNATURES-1];
} rbnewviews_t;

typedef struct _rbstore_t
{
  Session session;
  View    view;
  hash_t  hash;
} rbstore_t;

typedef struct _rbstore_auth_t
{
  rbstore_t store;
  auth_t    auth;
} rbstore_auth_t;

typedef struct _rbstore_auths_t
{
  rbstore_t store;
  auths_t   auths;
} rbstore_auths_t;

typedef struct _pm_sync_t
{
  View   view;
  hash_t hash;
  auth_t auth;
} pm_sync_t;

typedef struct _pm_syncs_t
{
  View    view;
  hash_t  hash;
  auths_t auths;
} pm_syncs_t;

#endif
