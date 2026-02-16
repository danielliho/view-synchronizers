#include "Wish.h"

bool Wish::operator<(const Wish& s) const {
  return ((session < s.session)
          || (session == s.session && auth < s.auth));
}

void Wish::serialize(salticidae::DataStream &data) const {
  data << this->session << this->hash << this->auth;
}

void Wish::unserialize(salticidae::DataStream &data) {
  data >> this->session >> this->hash >> this->auth;
}

Wish::Wish() {}

Wish::Wish(Session session, Hash hash, Auth auth) {
  this->session = session;
  this->hash    = hash;
  this->auth    = auth;
}

std::string Wish::toString() {
  std::string s = std::to_string(this->session) + this->hash.toString() + this->auth.toString();
  return s;
}

std::string Wish::prettyPrint() {
  return "W[" + std::to_string(this->session) + "," + this->hash.prettyPrint() + "," + this->auth.prettyPrint() + "]";
}

Session Wish::getSession() { return this->session; }
Hash    Wish::getHash()    { return this->hash;    }
Auth    Wish::getAuth()    { return this->auth;    }

bool Wish::operator==(const Wish& s) const {
  return (this->session == s.session && this->hash == s.hash && this->auth == s.auth);
}
