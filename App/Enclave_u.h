#ifndef ENCLAVE_U_H__
#define ENCLAVE_U_H__

#include <stdint.h>
#include <wchar.h>
#include <stddef.h>
#include <string.h>
#include "sgx_edger8r.h" /* for sgx_status_t etc. */

#include "../App/config.h"
#include "../App/types.h"
#include "../App/key.h"
#include "../Enclave/user_types.h"

#include <stdlib.h> /* for size_t */

#define SGX_CAST(type, item) ((type)(item))

#ifdef __cplusplus
extern "C" {
#endif

#ifndef OCALL_PRINT_DEFINED__
#define OCALL_PRINT_DEFINED__
void SGX_UBRIDGE(SGX_NOCONVENTION, ocall_print, (const char* str));
#endif
#ifndef OCALL_TEST_DEFINED__
#define OCALL_TEST_DEFINED__
void SGX_UBRIDGE(SGX_NOCONVENTION, ocall_test, (KEY* key));
#endif
#ifndef OCALL_SETCTIME_DEFINED__
#define OCALL_SETCTIME_DEFINED__
void SGX_UBRIDGE(SGX_NOCONVENTION, ocall_setCtime, (void));
#endif
#ifndef OCALL_RECCSTIME_DEFINED__
#define OCALL_RECCSTIME_DEFINED__
void SGX_UBRIDGE(SGX_NOCONVENTION, ocall_recCStime, (void));
#endif
#ifndef OCALL_RECCVTIME_DEFINED__
#define OCALL_RECCVTIME_DEFINED__
void SGX_UBRIDGE(SGX_NOCONVENTION, ocall_recCVtime, (void));
#endif
#ifndef U_SGXSSL_FTIME_DEFINED__
#define U_SGXSSL_FTIME_DEFINED__
void SGX_UBRIDGE(SGX_NOCONVENTION, u_sgxssl_ftime, (void* timeptr, uint32_t timeb_len));
#endif
#ifndef SGX_OC_CPUIDEX_DEFINED__
#define SGX_OC_CPUIDEX_DEFINED__
void SGX_UBRIDGE(SGX_CDECL, sgx_oc_cpuidex, (int cpuinfo[4], int leaf, int subleaf));
#endif
#ifndef SGX_THREAD_WAIT_UNTRUSTED_EVENT_OCALL_DEFINED__
#define SGX_THREAD_WAIT_UNTRUSTED_EVENT_OCALL_DEFINED__
int SGX_UBRIDGE(SGX_CDECL, sgx_thread_wait_untrusted_event_ocall, (const void* self));
#endif
#ifndef SGX_THREAD_SET_UNTRUSTED_EVENT_OCALL_DEFINED__
#define SGX_THREAD_SET_UNTRUSTED_EVENT_OCALL_DEFINED__
int SGX_UBRIDGE(SGX_CDECL, sgx_thread_set_untrusted_event_ocall, (const void* waiter));
#endif
#ifndef SGX_THREAD_SETWAIT_UNTRUSTED_EVENTS_OCALL_DEFINED__
#define SGX_THREAD_SETWAIT_UNTRUSTED_EVENTS_OCALL_DEFINED__
int SGX_UBRIDGE(SGX_CDECL, sgx_thread_setwait_untrusted_events_ocall, (const void* waiter, const void* self));
#endif
#ifndef SGX_THREAD_SET_MULTIPLE_UNTRUSTED_EVENTS_OCALL_DEFINED__
#define SGX_THREAD_SET_MULTIPLE_UNTRUSTED_EVENTS_OCALL_DEFINED__
int SGX_UBRIDGE(SGX_CDECL, sgx_thread_set_multiple_untrusted_events_ocall, (const void** waiters, size_t total));
#endif
#ifndef PTHREAD_WAIT_TIMEOUT_OCALL_DEFINED__
#define PTHREAD_WAIT_TIMEOUT_OCALL_DEFINED__
int SGX_UBRIDGE(SGX_CDECL, pthread_wait_timeout_ocall, (unsigned long long waiter, unsigned long long timeout));
#endif
#ifndef PTHREAD_CREATE_OCALL_DEFINED__
#define PTHREAD_CREATE_OCALL_DEFINED__
int SGX_UBRIDGE(SGX_CDECL, pthread_create_ocall, (unsigned long long self));
#endif
#ifndef PTHREAD_WAKEUP_OCALL_DEFINED__
#define PTHREAD_WAKEUP_OCALL_DEFINED__
int SGX_UBRIDGE(SGX_CDECL, pthread_wakeup_ocall, (unsigned long long waiter));
#endif

sgx_status_t initialize_variables(sgx_enclave_id_t eid, sgx_status_t* retval, PID* me, pids_t* others, unsigned int* q);
sgx_status_t TEEsign(sgx_enclave_id_t eid, sgx_status_t* retval, just_t* just);
sgx_status_t TEEprepare(sgx_enclave_id_t eid, sgx_status_t* retval, hash_t* hash, just_t* just, just_t* res);
sgx_status_t TEEstore(sgx_enclave_id_t eid, sgx_status_t* retval, just_t* just, just_t* res);
sgx_status_t TEEaccum(sgx_enclave_id_t eid, sgx_status_t* retval, votes_t* vs, accum_t* res);
sgx_status_t TEEaccumSp(sgx_enclave_id_t eid, sgx_status_t* retval, uvote_t* vote, accum_t* res);
sgx_status_t COMB_TEEsign(sgx_enclave_id_t eid, sgx_status_t* retval, just_t* just);
sgx_status_t COMB_TEEprepare(sgx_enclave_id_t eid, sgx_status_t* retval, hash_t* hash, accum_t* acc, just_t* res);
sgx_status_t COMB_TEEstore(sgx_enclave_id_t eid, sgx_status_t* retval, just_t* just, just_t* res);
sgx_status_t COMB_TEEaccum(sgx_enclave_id_t eid, sgx_status_t* retval, onejusts_t* js, accum_t* res);
sgx_status_t COMB_TEEaccumSp(sgx_enclave_id_t eid, sgx_status_t* retval, just_t* just, accum_t* res);
sgx_status_t FREE_TEEauth(sgx_enclave_id_t eid, sgx_status_t* retval, payload_t* text, auth_t* res);
sgx_status_t FREE_TEEverify(sgx_enclave_id_t eid, sgx_status_t* retval, payload_t* text, auths_t* a, bool* res);
sgx_status_t FREE_TEEverify2(sgx_enclave_id_t eid, sgx_status_t* retval, payload_t* text1, auths_t* a1, payload_t* text2, auths_t* a2, bool* res);
sgx_status_t FREE_TEEstore(sgx_enclave_id_t eid, sgx_status_t* retval, pjust_t* just, fvjust_t* res);
sgx_status_t FREE_TEEaccum(sgx_enclave_id_t eid, sgx_status_t* retval, fjust_t* j, fjusts_t* js, hash_t* prp, haccum_t* res);
sgx_status_t FREE_TEEaccumSp(sgx_enclave_id_t eid, sgx_status_t* retval, ofjust_t* just, hash_t* prp, haccum_t* res);
sgx_status_t FREE_initialize_variables(sgx_enclave_id_t eid, sgx_status_t* retval, PID* me, unsigned int* q);
sgx_status_t TEEpmSync(sgx_enclave_id_t eid, sgx_status_t* retval, fvjust_t* just, pm_sync_t* res);
sgx_status_t TEEpmSyncVote(sgx_enclave_id_t eid, sgx_status_t* retval, pm_sync_t* sync, pm_sync_t* res);
sgx_status_t TEEpmSyncEnd(sgx_enclave_id_t eid, sgx_status_t* retval, pm_syncs_t* votes, fvjust_t* res);
sgx_status_t ROTE_TEEauthView(sgx_enclave_id_t eid, sgx_status_t* retval, auth_t* res);
sgx_status_t OP_TEEverify(sgx_enclave_id_t eid, sgx_status_t* retval, payload_t* text, auths_t* a, bool* res);
sgx_status_t OP_TEEprepare(sgx_enclave_id_t eid, sgx_status_t* retval, hash_t* hash, opproposal_t* res);
sgx_status_t OP_TEEvote(sgx_enclave_id_t eid, sgx_status_t* retval, hash_t* hash, opvote_t* res);
sgx_status_t OP_TEEstore(sgx_enclave_id_t eid, sgx_status_t* retval, opproposal_t* just, opstore_t* res);
sgx_status_t OP_TEEaccum(sgx_enclave_id_t eid, sgx_status_t* retval, opstore_t* j, opstores_t* js, opaccum_t* res);
sgx_status_t OP_TEEaccumSp(sgx_enclave_id_t eid, sgx_status_t* retval, opprepare_t* just, opaccum_t* res);
sgx_status_t OP_initialize_variables(sgx_enclave_id_t eid, sgx_status_t* retval, PID* me, unsigned int* q);
sgx_status_t CH_TEEsign(sgx_enclave_id_t eid, sgx_status_t* retval, just_t* just);
sgx_status_t CH_TEEprepare(sgx_enclave_id_t eid, sgx_status_t* retval, jblock_t* block, jblock_t* block0, jblock_t* block1, just_t* res);
sgx_status_t CH_COMB_TEEsign(sgx_enclave_id_t eid, sgx_status_t* retval, just_t* just);
sgx_status_t CH_COMB_TEEprepare(sgx_enclave_id_t eid, sgx_status_t* retval, cblock_t* block, hash_t* hash, just_t* res);
sgx_status_t CH_COMB_TEEaccum(sgx_enclave_id_t eid, sgx_status_t* retval, onejusts_t* js, accum_t* res);
sgx_status_t CH_COMB_TEEaccumSp(sgx_enclave_id_t eid, sgx_status_t* retval, just_t* just, accum_t* res);
sgx_status_t TEEinitializeRB(sgx_enclave_id_t eid, sgx_status_t* retval, PID* me, rbstore_auth_t* p);
sgx_status_t TEEsync(sgx_enclave_id_t eid, sgx_status_t* retval, rbstore_auth_t* p, sync_t* res);
sgx_status_t TEEjoinRequest(sgx_enclave_id_t eid, sgx_status_t* retval, Session* s, join_t* res);
sgx_status_t TEEsyncVote(sgx_enclave_id_t eid, sgx_status_t* retval, rbaccum_sync_auth_t* acc, inonces_t* nonces, sync_vote_auth_t* res);
sgx_status_t TEEsyncEnd(sgx_enclave_id_t eid, sgx_status_t* retval, sync_vote_auths_t* qc, rbstore_auth_t* res);
sgx_status_t TEEspSyncVote(sgx_enclave_id_t eid, sgx_status_t* retval, rbaccum_sync_auth_t* acc, sp_sync_vote_auth_t* res);
sgx_status_t TEEspSyncEnd(sgx_enclave_id_t eid, sgx_status_t* retval, sp_sync_vote_auths_t* qc, rbstore_auth_t* res);
sgx_status_t TEEprepareRB(sgx_enclave_id_t eid, sgx_status_t* retval, hash_t* hblock, rbprepare_auth_t* res);
sgx_status_t TEEstoreRB(sgx_enclave_id_t eid, sgx_status_t* retval, rbprepare_auths_t* prep, rbstore_auth_t* res);
sgx_status_t TEEnewviewRB(sgx_enclave_id_t eid, sgx_status_t* retval, rbstore_auth_t* store, rbnewview_auth_t* res);
sgx_status_t TEEaccumNvRB(sgx_enclave_id_t eid, sgx_status_t* retval, rbnewview_auth_t* j, rbnewviews_t* js, rbaccum_nv_auth_t* res);
sgx_status_t TEEaccumSyncRB(sgx_enclave_id_t eid, sgx_status_t* retval, sync_t* j, syncs_t* js, rbaccum_sync_auth_t* res);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif
