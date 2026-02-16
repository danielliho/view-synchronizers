#ifndef INONCE_H
#define INONCE_H

#include "types.h"
#include "config.h"
#include "Hash.h"
#include "Auth.h"

#include "salticidae/stream.h"


// Id + Nonce
class INonce {

 private:
  PID id;
  Hash nonce;

 public:
  INonce();
  INonce(PID id, Hash nonce);

  PID  getId();
  Hash getNonce();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string toString();
  std::string prettyPrint();

  bool operator<(const INonce& s) const;
  bool operator==(const INonce& s) const;
};

#endif
