#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <string>
#include <cstring>

#include "SyncVoteAuth.h"

SyncVote SyncVoteAuth::getVote() { return (this->vote); }
Auth     SyncVoteAuth::getAuth() { return (this->auth); }

void SyncVoteAuth::serialize(salticidae::DataStream &data) const {
  data << this->vote << this->auth;
}

void SyncVoteAuth::unserialize(salticidae::DataStream &data) {
  data >> this->vote >> this->auth;
}

SyncVoteAuth::SyncVoteAuth(SyncVote vote, Auth auth) {
  this->vote = vote;
  this->auth = auth;
}

SyncVoteAuth::SyncVoteAuth() {
  this->vote = SyncVote();
  this->auth = Auth();
}

std::string SyncVoteAuth::prettyPrint() {
  return ("SYNC-VOTE-AUTH[" + (this->vote).prettyPrint()
          + "," + (this->auth).prettyPrint()
          + "]");
}

std::string SyncVoteAuth::toString() {
  return ((this->vote).toString()
          + (this->auth).toString());
}

bool SyncVoteAuth::operator<(const SyncVoteAuth& s) const {
  return (vote < s.vote
          || (vote == s.vote && auth < s.auth));
}

bool SyncVoteAuth::operator==(const SyncVoteAuth& s) const {
  return (vote == s.vote && auth == s.auth);
}
