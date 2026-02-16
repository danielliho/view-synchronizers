#ifndef RBPREPAREAUTH_H
#define RBPREPAREAUTH_H

#include "RBprepare.h"
#include "Auth.h"

#include "salticidae/stream.h"

// a prepare certificate (rollback prevention)
class RBprepareAuth {

 private:
  RBprepare prep;
  Auth      auth;

 public:
  RBprepareAuth();
  RBprepareAuth(RBprepare prep, Auth auth);

  RBprepare getPrepare();
  Auth      getAuth();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();
  std::string data();

  bool operator<(const RBprepareAuth& s) const;
};


#endif
