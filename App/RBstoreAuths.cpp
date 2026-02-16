#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <string>
#include <cstring>

#include "RBstoreAuths.h"


RBstore RBstoreAuths::getStore() { return (this->store); }
Auths   RBstoreAuths::getAuths() { return (this->auths); }


void RBstoreAuths::serialize(salticidae::DataStream &data) const {
  data << this->store << this->auths;
}


void RBstoreAuths::unserialize(salticidae::DataStream &data) {
  data >> this->store >> this->auths;
}


RBstoreAuths::RBstoreAuths(RBstore store, Auths auths) {
  this->store = store;
  this->auths = auths;
}


RBstoreAuths::RBstoreAuths() {}


void RBstoreAuths::add(Auth a) {
  this->auths.add(a);
}


std::string RBstoreAuths::prettyPrint() {
  return ("STORE-AUTH[" + (this->store).prettyPrint()
          + "," + (this->auths).prettyPrint()
          + "]");
}

std::string RBstoreAuths::toString() {
  return ((this->store).toString()
          + (this->auths).toString());
}

std::string RBstoreAuths::data() {
  return ((this->store).toString()
          + (this->auths).toString());
}

bool RBstoreAuths::operator<(const RBstoreAuths& s) const {
  return (store < s.store
          || (store == s.store && auths < s.auths));
}

bool RBstoreAuths::operator==(const RBstoreAuths& s) const {
  return (store == s.store && auths == s.auths);
}
