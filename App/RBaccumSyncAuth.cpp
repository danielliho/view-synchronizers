#include "RBaccumSyncAuth.h"
#include <iostream>


RBaccumSyncAuth::RBaccumSyncAuth() {
  this->acc  = RBaccumSync();
  this->auth = Auth();
}

RBaccumSyncAuth::RBaccumSyncAuth(RBaccumSync acc, Auth auth) {
  this->acc  = acc;
  this->auth = auth;
}

RBaccumSync RBaccumSyncAuth::getAcc()  { return this->acc;  }
Auth      RBaccumSyncAuth::getAuth() { return this->auth; }


void RBaccumSyncAuth::serialize(salticidae::DataStream &data) const {
  data << this->acc << this->auth;
}


void RBaccumSyncAuth::unserialize(salticidae::DataStream &data) {
  data >> this->acc >> this->auth;
}

std::string RBaccumSyncAuth::prettyPrint() {
  return ("ACCUM-AUTH["
          + (this->acc).prettyPrint()
          + "," + (this->auth).prettyPrint()
          + "]");
}

std::string RBaccumSyncAuth::toString() {
  return ((this->acc).toString()
          + (this->auth).toString());
}

std::string RBaccumSyncAuth::data() {
  return ((this->acc).toString()
          + (this->auth).toString());
}

bool RBaccumSyncAuth::operator<(const RBaccumSyncAuth& s) const {
  return ((acc < s.acc)
          || ((acc == s.acc && auth < s.auth)));
}

bool RBaccumSyncAuth::operator==(const RBaccumSyncAuth& s) const {
  return (acc == s.acc
          && auth == s.auth);
}
