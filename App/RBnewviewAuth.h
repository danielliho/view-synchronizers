#ifndef RBNEWVIEWAUTH_H
#define RBNEWVIEWAUTH_H

#include "RBnewview.h"
#include "Auth.h"

#include "salticidae/stream.h"

// a newview certificate (rollback prevention)
class RBnewviewAuth {

 private:
  RBnewview newview;
  Auth      auth;

 public:
  RBnewviewAuth();
  RBnewviewAuth(RBnewview prep, Auth auth);

  RBnewview getNewview();
  Auth      getAuth();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();
  std::string data();

  bool operator==(const RBnewviewAuth& s) const;
  bool operator<(const RBnewviewAuth& s) const;
};


#endif
