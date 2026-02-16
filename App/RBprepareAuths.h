#ifndef RBPREPAREAUTHS_H
#define RBPREPAREAUTHS_H

#include "RBprepare.h"
#include "Auths.h"

#include "salticidae/stream.h"

// a prepare certificate (rollback prevention)
class RBprepareAuths {

 private:
  RBprepare prep;
  Auths     auths;

 public:
  RBprepareAuths();
  RBprepareAuths(RBprepare prep, Auths auths);

  RBprepare getPrepare();
  Auths     getAuths();

  void add(Auth auth);

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();
  std::string data();

  bool operator<(const RBprepareAuths& s) const;
};


#endif
