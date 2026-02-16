#include "RBaccumNvAuth.h"
#include <iostream>


RBaccumNvAuth::RBaccumNvAuth() {
  this->acc  = RBaccumNv();
  this->auth = Auth();
}

RBaccumNvAuth::RBaccumNvAuth(RBaccumNv acc, Auth auth) {
  this->acc  = acc;
  this->auth = auth;
}

RBaccumNv RBaccumNvAuth::getAcc()  { return this->acc;  }
Auth      RBaccumNvAuth::getAuth() { return this->auth; }


void RBaccumNvAuth::serialize(salticidae::DataStream &data) const {
  data << this->acc << this->auth;
}


void RBaccumNvAuth::unserialize(salticidae::DataStream &data) {
  data >> this->acc >> this->auth;
}

std::string RBaccumNvAuth::prettyPrint() {
  return ("ACCUM-AUTH["
          + (this->acc).prettyPrint()
          + "," + (this->auth).prettyPrint()
          + "]");
}

std::string RBaccumNvAuth::toString() {
  return ((this->acc).toString()
          + (this->auth).toString());
}

std::string RBaccumNvAuth::data() {
  return ((this->acc).toString()
          + (this->auth).toString());
}

bool RBaccumNvAuth::operator<(const RBaccumNvAuth& s) const {
  return ((acc < s.acc)
          || ((acc == s.acc && auth < s.auth)));
}

bool RBaccumNvAuth::operator==(const RBaccumNvAuth& s) const {
  return (acc == s.acc
          && auth == s.auth);
}
