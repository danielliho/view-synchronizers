#ifndef JOIN_H
#define JOIN_H

#include "types.h"
#include "config.h"
#include "Hash.h"
#include "Auth.h"

#include "salticidae/stream.h"


class Join {

 private:
  Session session;
  Hash    nonce;
  Auth    auth;

 public:
  Join();
  Join(Session session, Hash nonce, Auth auth);

  Session getSession();
  Hash    getNonce();
  Auth    getAuth();

  Hash hash();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string toString();
  std::string prettyPrint();

  bool operator<(const Join& s) const;
  bool operator==(const Join& s) const;
};

#endif
