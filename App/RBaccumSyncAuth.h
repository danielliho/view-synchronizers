#ifndef RBACCUMSYNCAUTH_H
#define RBACCUMSYNCAUTH_H

#include "RBaccumSync.h"
#include "Auth.h"

#include "salticidae/stream.h"

// a prepare certificate (rollback prevention)
class RBaccumSyncAuth {

 private:
  RBaccumSync acc;
  Auth      auth;

 public:
  RBaccumSyncAuth();
  RBaccumSyncAuth(RBaccumSync acc, Auth auth);

  RBaccumSync getAcc();
  Auth        getAuth();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();
  std::string data();

  bool operator<(const RBaccumSyncAuth& s) const;
  bool operator==(const RBaccumSyncAuth& s) const;
};


#endif
