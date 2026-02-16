#ifndef RBACCUMNVAUTH_H
#define RBACCUMNVAUTH_H

#include "RBaccumNv.h"
#include "Auth.h"

#include "salticidae/stream.h"

// a prepare certificate (rollback prevention)
class RBaccumNvAuth {

 private:
  RBaccumNv acc;
  Auth      auth;

 public:
  RBaccumNvAuth();
  RBaccumNvAuth(RBaccumNv acc, Auth auth);

  RBaccumNv getAcc();
  Auth      getAuth();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();
  std::string data();

  bool operator<(const RBaccumNvAuth& s) const;
  bool operator==(const RBaccumNvAuth& s) const;
};


#endif
