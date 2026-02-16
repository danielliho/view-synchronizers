#ifndef WISH_H
#define WISH_H

#include "types.h"
#include "config.h"
#include "Hash.h"
#include "Auth.h"

#include "salticidae/stream.h"


class Wish {

 private:
  Session session;
  Hash    hash;
  Auth    auth;

 public:
  Wish();
  Wish(Session session, Hash hash, Auth auth);

  Session getSession();
  Hash    getHash();
  Auth    getAuth();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string toString();
  std::string prettyPrint();

  bool operator<(const Wish& s) const;
  bool operator==(const Wish& s) const;
};

#endif
