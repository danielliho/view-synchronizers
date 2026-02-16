#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <string>
#include <cstring>

#include "Join.h"

bool Join::operator<(const Join& s) const {
  return ((session < s.session)
          || (session == s.session && auth < s.auth));
}

void Join::serialize(salticidae::DataStream &data) const {
  data << this->session << this->nonce << this->auth;
}

void Join::unserialize(salticidae::DataStream &data) {
  data >> this->session >> this->nonce >> this->auth;
}

Join::Join() {
  this->session = 0;
  this->nonce   = Hash(false);
  this->auth    = Auth(false);
}

Join::Join(Session session, Hash nonce, Auth auth) {
  this->session = session;
  this->nonce   = nonce;
  this->auth    = auth;
}

std::string Join::toString() {
  return (std::to_string(this->session)
          + this->nonce.toString()
          + this->auth.toString());
}

std::string Join::prettyPrint() {
  return ("J[" + std::to_string(this->session)
          + "," + this->nonce.prettyPrint()
          + "," + this->auth.prettyPrint()
          + "]");
}

Session Join::getSession() { return this->session; }
Hash    Join::getNonce()   { return this->nonce;   }
Auth    Join::getAuth()    { return this->auth;    }

Hash Join::hash() {
  unsigned char h[SHA256_DIGEST_LENGTH];
  std::string text = this->toString();

  if (!SHA256 ((const unsigned char *)text.c_str(), text.size(), h)){
    std::cout << KCYN << "SHA1 failed" << KNRM << std::endl;
    exit(0);
  }
  return Hash(h);
}

bool Join::operator==(const Join& s) const {
  return (this->session == s.session
          && this->nonce == s.nonce
          && this->auth == s.auth);
}
