#ifndef RBACCUMSYNC_H
#define RBACCUMSYNC_H

#include "Hash.h"

#include "salticidae/stream.h"

// an accumulator (rollback prevention)
class RBaccumSync {

 private:
  Session session;
  View    view;
  Hash    hash;

 public:
  RBaccumSync();
  RBaccumSync(Session session, View view, Hash hash);

  Session  getSession();
  View     getView();
  Hash     getHash();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();
  std::string data();

  bool operator<(const RBaccumSync& s) const;
  bool operator==(const RBaccumSync& s) const;
};


#endif
