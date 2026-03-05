#ifndef SYNC_H
#define SYNC_H

#include "types.h"
#include "config.h"
#include "Hash.h"
#include "Auth.h"

#include "salticidae/stream.h"


class Sync {

 private:
  Session session;
  View view;
  Hash block;
  Auth auth;

 public:
  Sync();
  Sync(Session session, View view, Hash block, Auth auth);

  Session getSession();
  View getView();
  Hash getBlock();
  Auth getAuth();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string toString();
  std::string prettyPrint();

  bool operator<(const Sync& s) const;
  bool operator==(const Sync& s) const;
};

#endif
