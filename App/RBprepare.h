#ifndef RBPREPARE_H
#define RBPREPARE_H

#include "Hash.h"

#include "salticidae/stream.h"

// a prepare certificate (rollback prevention)
class RBprepare {

 private:
  Session session;
  View    view; // View at which the certifiate was created
  Hash    hash;

 public:
  RBprepare();
  RBprepare(Session session, View view, Hash hash);

  Session  getSession();
  View     getView();
  Hash     getHash();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();
  std::string data();

  bool operator<(const RBprepare& s) const;
  bool operator==(const RBprepare& s) const;
};


#endif
