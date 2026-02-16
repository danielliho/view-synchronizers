#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <string>
#include <cstring>

#include "RBstoreAuth.h"


RBstore RBstoreAuth::getStore() { return (this->store); }
Auth    RBstoreAuth::getAuth()  { return (this->auth);  }


void RBstoreAuth::serialize(salticidae::DataStream &data) const {
  data << this->store << this->auth;
}


void RBstoreAuth::unserialize(salticidae::DataStream &data) {
  data >> this->store >> this->auth;
}


RBstoreAuth::RBstoreAuth(RBstore store, Auth auth) {
  this->store = store;
  this->auth  = auth;
}


RBstoreAuth::RBstoreAuth() {}


std::string RBstoreAuth::prettyPrint() {
  return ("STORE-AUTH[" + (this->store).prettyPrint()
          + "," + (this->auth).prettyPrint()
          + "]");
}

std::string RBstoreAuth::toString() {
  return ((this->store).toString()
          + (this->auth).toString());
}

std::string RBstoreAuth::data() {
  return ((this->store).toString()
          + (this->auth).toString());
}

bool RBstoreAuth::operator<(const RBstoreAuth& s) const {
  return (store < s.store
          || (store == s.store && auth < s.auth));
}

bool RBstoreAuth::operator==(const RBstoreAuth& s) const {
  return (store == s.store && auth == s.auth);
}
