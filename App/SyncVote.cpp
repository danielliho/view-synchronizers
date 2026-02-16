#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <string>
#include <cstring>

#include "SyncVote.h"

bool SyncVote::operator<(const SyncVote& s) const {
  return (session < s.session || (session == s.session && view < s.view));
}

void SyncVote::serialize(salticidae::DataStream &data) const {
  data << this->session << this->view << this->block << this->joins;
}

void SyncVote::unserialize(salticidae::DataStream &data) {
  data >> this->session >> this->view >> this->block >> this->joins;
}

SyncVote::SyncVote() {
  this->session = 0;
  this->view    = 0;
  this->block   = Hash(false);
  this->joins   = INonces();
}

SyncVote::SyncVote(Session session, View view, Hash block, INonces joins) {
  this->session = session;
  this->view    = view;
  this->block   = block;
  this->joins   = joins;
}

std::string SyncVote::toString() {
  std::string s = (std::to_string(this->session)
                   + std::to_string(this->view)
                   + this->block.toString()
                   + this->joins.toString());
  return s;
}

std::string SyncVote::prettyPrint() {
  return "SYNC-VOTE[" + std::to_string(this->session)
    + "," + std::to_string(this->view)
    + "," + this->block.prettyPrint()
    + "," + this->joins.prettyPrint()
    + "]";
}

Session SyncVote::getSession() { return this->session; }
View    SyncVote::getView()    { return this->view;    }
Hash    SyncVote::getBlock()   { return this->block;   }
INonces SyncVote::getJoins()   { return this->joins;   }

bool SyncVote::operator==(const SyncVote& s) const {
  bool b1 = this->session == s.session;
  bool b2 = this->view == s.view;
  bool b3 = this->block == s.block;
  bool b4 = this->joins == s.joins;
  std::cout << KCYN << "comparing SynVotes:" << b1 << "," << b2 << "," << b2 << "," << b4 << KNRM << std::endl;
  return (b1 && b2 && b3 && b4);
}
