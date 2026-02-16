#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <string>
#include <cstring>

#include "INonce.h"

bool INonce::operator<(const INonce& s) const {
  return (id < s.id);
}

bool INonce::operator==(const INonce& s) const {
  return (this->id == s.id
          && this->nonce == s.nonce);
}

void INonce::serialize(salticidae::DataStream &data) const {
  data << this->id << this->nonce;
}

void INonce::unserialize(salticidae::DataStream &data) {
  data >> this->id >> this->nonce;
}

INonce::INonce() {
  this->id    = 0;
  this->nonce = Hash(false);
}

INonce::INonce(PID id, Hash nonce) {
  this->id    = id;
  this->nonce = nonce;
}

std::string INonce::toString() {
  return (std::to_string(this->id)
          + this->nonce.toString());
}

std::string INonce::prettyPrint() {
  return ("INONCE[" + std::to_string(this->id)
          + "," + this->nonce.prettyPrint()
          + "]");
}

PID  INonce::getId()    { return this->id;    }
Hash INonce::getNonce() { return this->nonce; }
