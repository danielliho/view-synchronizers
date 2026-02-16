#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <string>
#include <cstring>

#include "SyncVoteAuths.h"


SyncVote SyncVoteAuths::getVote()  { return (this->vote);  }
Auths    SyncVoteAuths::getAuths() { return (this->auths); }


void SyncVoteAuths::serialize(salticidae::DataStream &data) const {
  data << this->vote << this->auths;
}


void SyncVoteAuths::unserialize(salticidae::DataStream &data) {
  data >> this->vote >> this->auths;
}


SyncVoteAuths::SyncVoteAuths(SyncVote vote, Auths auths) {
  this->vote  = vote;
  this->auths = auths;
}


SyncVoteAuths::SyncVoteAuths() {
  this->vote  = SyncVote();
  this->auths = Auths();
}


std::string SyncVoteAuths::prettyPrint() {
  return ("SYNC-VOTE-AUTH[" + (this->vote).prettyPrint()
          + "," + (this->auths).prettyPrint()
          + "]");
}

std::string SyncVoteAuths::toString() {
  return ((this->vote).toString()
          + (this->auths).toString());
}

bool SyncVoteAuths::operator<(const SyncVoteAuths& s) const {
  return (vote < s.vote
          || (vote == s.vote && auths < s.auths));
}

bool SyncVoteAuths::operator==(const SyncVoteAuths& s) const {
  return (vote == s.vote && auths == s.auths);
}
