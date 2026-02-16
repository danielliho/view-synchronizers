#ifndef RBSTOREAUTHS_H
#define RBSTOREAUTHS_H


#include "RBstore.h"
#include "Auths.h"

#include "salticidae/stream.h"


// OnePhase store certificate
class RBstoreAuths {
 private:
  RBstore store;
  Auths   auths;

 public:
  RBstoreAuths(RBstore store, Auths auths);
  RBstoreAuths();

  RBstore getStore();
  Auths   getAuths();

  void add(Auth auth);

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();
  std::string data();

  bool operator<(const RBstoreAuths& s) const;
  bool operator==(const RBstoreAuths& s) const;
};


#endif
