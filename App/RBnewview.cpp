#include <stdio.h>
#include <stdlib.h>
#include <iostream>

#include "RBnewview.h"


Session RBnewview::getSession() { return (this->session); }
View    RBnewview::getView()    { return (this->view);    }
View    RBnewview::getPrepv()   { return (this->prepv);   }
Hash    RBnewview::getHash()    { return (this->hash);    }

void RBnewview::serialize(salticidae::DataStream &data) const {
  data << this->session << this->view << this->prepv << this->hash;
}

void RBnewview::unserialize(salticidae::DataStream &data) {
  data >> this->session >> this->view >> this->prepv >> this->hash;
}

RBnewview::RBnewview(Session session, View view, View prepv, Hash hash) {
  this->session = session;
  this->view    = view;
  this->prepv   = prepv;
  this->hash    = hash;
}

RBnewview::RBnewview() {
  this->session = 0;
  this->view    = 0;
  this->prepv   = 0;
  this->hash    = Hash(false);
}

RBnewview::RBnewview(salticidae::DataStream &data) {
  unserialize(data);
}

std::string RBnewview::prettyPrint() {
  return ("RB-NEW-VIEW[" + std::to_string(this->session)
          + "," + std::to_string(this->view)
          + "," + std::to_string(this->prepv)
          + "," + (this->hash).prettyPrint()
          + "]");
}

std::string RBnewview::toString() {
  return (std::to_string(this->session)
          + std::to_string(this->view)
          + std::to_string(this->prepv)
          + (this->hash).toString());
}

bool RBnewview::operator==(const RBnewview& s) const {
  if (DEBUG2) {
    std::cout << KYEL
              << "[1]" << (this->session == s.session)
              << "[2]" << (this->view    == s.view)
              << "[3]" << (this->view    == s.prepv)
              << "[4]" << (this->hash    == s.hash)
              << KNRM << std::endl;
  }
  return (this->session == s.session
          && this->view == s.view
          && this->prepv == s.prepv
          && this->hash == s.hash);
}

bool RBnewview::operator<(const RBnewview& s) const {
  return ((this->session < s.session)
          || (this->session == s.session && this->view < s.view)
          || (this->session == s.session && this->view == s.view && this->prepv < s.prepv));
}
