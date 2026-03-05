#ifndef SYNCVOTE_H
#define SYNCVOTE_H

#include "types.h"
#include "config.h"
#include "Hash.h"
#include "INonces.h"

#include "salticidae/stream.h"


class SyncVote {

 private:
  Session session;
  View view;
  Hash block;
  INonces joins;

 public:
  SyncVote();
  SyncVote(Session session, View view, Hash block, INonces joins);

  Session getSession();
  View getView();
  Hash getBlock();
  INonces getJoins();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string toString();
  std::string prettyPrint();

  bool operator<(const SyncVote& s) const;
  bool operator==(const SyncVote& s) const;
};

#endif
