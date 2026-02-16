#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <string>
#include <cstring>

#include "RBstore.h"


Session RBstore::getSession() { return (this->session); }
View    RBstore::getView()    { return (this->view);    }
Hash    RBstore::getHash()    { return (this->hash);    }


void RBstore::serialize(salticidae::DataStream &data) const {
  data << this->session << this->view << this->hash;
}


void RBstore::unserialize(salticidae::DataStream &data) {
  data >> this->session >> this->view >> this->hash;
}


RBstore::RBstore(Session session, View view, Hash hash) {
  this->session = session;
  this->view    = view;
  this->hash    = hash;
}


RBstore::RBstore() {
  this->session = 0;
  this->view    = 0;
  this->hash    = Hash(false);
}


std::string RBstore::prettyPrint() {
  return ("STORE[" + std::to_string(this->session)
          + "," + std::to_string(this->view)
          + "," + (this->hash).prettyPrint()
          + "]");
}

std::string RBstore::toString() {
  return (std::to_string(this->session)
          + std::to_string(this->view)
          + (this->hash).toString());
}

std::string RBstore::data() {
  return toString();
}

bool RBstore::operator<(const RBstore& s) const {
  return (session < s.session
          || (session == s.session && view < s.view));
}

bool RBstore::operator==(const RBstore& s) const {
  return (session == s.session && view == s.view && hash == s.hash);
}
