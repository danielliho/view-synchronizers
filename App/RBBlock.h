#ifndef RBBLOCK_H
#define RBBLOCK_H

#include <vector>

#include "config.h"
#include "types.h"
#include "Hash.h"
#include "Joins.h"
#include "Transactions.h"

#include "salticidae/stream.h"


class RBBlock {
 private:
  unsigned int id; // id of the block
  bool set; // true if the block is not the dummy block
  Hash prevHash;
  Transactions transactions;
  Session session;
  Joins joins;

  std::string transactions2string();

 public:
  RBBlock(); // retruns the genesis block
  RBBlock(bool b); // retruns the genesis block if b=true; and the dummy block otherwise
  //Block(Hash prevHash);
  RBBlock(unsigned int id, Hash prevHash, Transactions transactions, Session session, Joins joins); // creates an extension of 'block'

  bool extends(Hash h);
  Hash hash();

  bool isDummy(); // true if the block is not set
  unsigned int getSize();
  Hash getPrevHash();
  Transactions getTransactions();
  Session getSession();
  Joins getJoins();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string toString();
  std::string prettyPrint();

  bool operator==(const RBBlock& s) const;
};


#endif
