#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <string>
#include <cstring>

#include "RBBlock.h"


void RBBlock::serialize(salticidae::DataStream &data) const {
  data << this->id << this->set << this->prevHash << this->transactions << this->session << this->joins;
}


void RBBlock::unserialize(salticidae::DataStream &data) {
  data >> this->id >> this->set >> this->prevHash >> this->transactions >> this->session >> this->joins;
}


std::string RBBlock::toString() {
  std::string text = std::to_string(this->id)
    + std::to_string(this->set)
    + this->prevHash.toString()
    + this->transactions.toString()
    + std::to_string(this->session)
    + this->joins.toString();
  return text;
}

std::string RBBlock::prettyPrint() {
  return ("BLOCK[" + std::to_string(this->id)
          + "," + std::to_string(this->set)
          + "," + this->prevHash.prettyPrint()
          //+ "," + this->transactions.prettyPrint()
          + "," + "[--transactions--]"
          + "," + std::to_string(this->session)
          + "," + this->joins.prettyPrint()
          + "]");
}


Hash RBBlock::hash() {
  unsigned char h[SHA256_DIGEST_LENGTH];
  std::string text = this->toString();

  if (!SHA256 ((const unsigned char *)text.c_str(), text.size(), h)){
    std::cout << KCYN << "SHA1 failed" << KNRM << std::endl;
    exit(0);
  }
  return Hash(h);
}


// checks whether this block extends the argument
bool RBBlock::extends(Hash h) {
  return (this->prevHash == h);
}

bool         RBBlock::isDummy()         { return !this->set;                   }
unsigned int RBBlock::getSize()         { return this->transactions.getSize(); }
Hash         RBBlock::getPrevHash()     { return this->prevHash;               }
Transactions RBBlock::getTransactions() { return this->transactions;           }
Session      RBBlock::getSession()      { return this->session;                }
Joins        RBBlock::getJoins()        { return this->joins;                  }


RBBlock::RBBlock(bool b) {
  this->prevHash=Hash();
  this->set=b;
}

RBBlock::RBBlock() {
  this->prevHash=Hash();
  this->set=true;
}

/*RBBlock::RBBlock(Hash prevHash) {
  this->prevHash=prevHash;
  this->set=true;
}*/

RBBlock::RBBlock(unsigned int id, Hash prevHash, Transactions transactions, Session session, Joins joins) {
  this->id           = id;
  this->set          = true;
  this->prevHash     = prevHash;
  this->transactions = transactions;
  this->session      = session;
  this->joins        = joins;
}

bool RBBlock::operator==(const RBBlock& s) const {
  return (this->id == s.id
          && this->set == s.set
          && this->prevHash == s.prevHash
          && this->transactions == s.transactions
          && this->session == s.session
          && this->joins == s.joins);
}
