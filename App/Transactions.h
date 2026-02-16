#ifndef TRANSACTIONS_H
#define TRANSACTIONS_H

#include <set>

#include "Hash.h"
#include "Transaction.h"

#include "salticidae/stream.h"


class Transactions {
  private:
    unsigned int size = 0;
    Transaction transactions[MAX_NUM_TRANSACTIONS];

  public:
    Transactions();
    Transactions(Transaction t);
    Transactions(unsigned int size, Transaction transactions[MAX_NUM_TRANSACTIONS]);
    Transactions(salticidae::DataStream &data);

    void serialize(salticidae::DataStream &data) const;
    void unserialize(salticidae::DataStream &data);

    std::string prettyPrint();
    std::string toString();

    unsigned int getSize();
    Transaction get(unsigned int i);
    void add(Transaction t);
    void addUpto(Transactions others, unsigned int n);

    bool operator<(const Transactions& s) const;
    bool operator==(const Transactions& s) const;
};


#endif
