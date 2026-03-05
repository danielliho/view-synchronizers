#ifndef SYNCVOTEAUTH_H
#define SYNCVOTEAUTH_H

#include "SyncVote.h"
#include "Auth.h"

#include "salticidae/stream.h"


class SyncVoteAuth {

 private:
  SyncVote vote;
  Auth auth;

 public:
  SyncVoteAuth();
  SyncVoteAuth(SyncVote vote, Auth auth);

  SyncVote getVote();
  Auth getAuth();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string toString();
  std::string prettyPrint();

  bool operator<(const SyncVoteAuth& s) const;
  bool operator==(const SyncVoteAuth& s) const;
};

#endif
