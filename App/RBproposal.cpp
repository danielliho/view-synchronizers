#include "RBproposal.h"
#include <iostream>


RBproposal::RBproposal() {
  this->block = Hash(false);
  this->acc   = RBaccumNvAuth();
}

RBproposal::RBproposal(Hash block, RBaccumNvAuth acc) {
  this->block = block;
  this->acc   = acc;
}

Hash          RBproposal::getBlock() { return this->block; }
RBaccumNvAuth RBproposal::getAcc()   { return this->acc;   }

void RBproposal::serialize(salticidae::DataStream &data) const {
  data << this->block << this->acc;
}

void RBproposal::unserialize(salticidae::DataStream &data) {
  data >> this->block >> this->acc;
}

std::string RBproposal::prettyPrint() {
  return ("RB-PROPOSAL[" + (this->block).prettyPrint()
          + "," + (this->acc).prettyPrint()
          + "]");
}

std::string RBproposal::toString() {
  return ((this->block).toString()
          + (this->acc).toString());
}

bool RBproposal::operator<(const RBproposal& s) const {
  return (acc < s.acc);
}

bool RBproposal::operator==(const RBproposal& s) const {
  return (block == s.block
          && acc == s.acc);
}
