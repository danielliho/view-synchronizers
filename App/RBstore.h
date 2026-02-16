#ifndef RBSTORE_H
#define RBSTORE_H


#include "Hash.h"

#include "salticidae/stream.h"


// OnePhase store certificate
class RBstore {
 private:
  Session session;
  View    view;
  Hash    hash;

 public:
  RBstore(Session session, View view, Hash hash);
  RBstore();

  Session getSession();
  View    getView();
  Hash    getHash();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();
  std::string data();

  bool operator<(const RBstore& s) const;
  bool operator==(const RBstore& s) const;
};


#endif
