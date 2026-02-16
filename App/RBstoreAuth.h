#ifndef RBSTOREAUTH_H
#define RBSTOREAUTH_H


#include "RBstore.h"
#include "Auth.h"

#include "salticidae/stream.h"


// OnePhase store certificate
class RBstoreAuth {
 private:
  RBstore store;
  Auth    auth;

 public:
  RBstoreAuth(RBstore store, Auth auth);
  RBstoreAuth();

  RBstore getStore();
  Auth    getAuth();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();
  std::string data();

  bool operator<(const RBstoreAuth& s) const;
  bool operator==(const RBstoreAuth& s) const;
};


#endif
