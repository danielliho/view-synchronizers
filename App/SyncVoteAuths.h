#ifndef SYNCVOTEAUTHS_H
#define SYNCVOTEAUTHS_H

#include "SyncVote.h"
#include "Auths.h"

#include "salticidae/stream.h"


class SyncVoteAuths {

 private:
  SyncVote vote;
  Auths auths;

 public:
  SyncVoteAuths();
  SyncVoteAuths(SyncVote vote, Auths auths);

  SyncVote getVote();
  Auths getAuths();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string toString();
  std::string prettyPrint();

  bool operator<(const SyncVoteAuths& s) const;
  bool operator==(const SyncVoteAuths& s) const;
};

#endif
