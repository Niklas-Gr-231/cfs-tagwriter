// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#include <cassert>
#include <iostream>
#include "Arduino.h"
#include "bridge.ino"
void fresh(){reader.reset();releaseCard();Serial.out.clear();Serial.in.clear();inputLength=0;discardLine=false;nowMs=0;}
std::string run(const std::string&s){char line[1024];std::strcpy(line,s.c_str());Serial.out.clear();handleCommand(line);return Serial.out;}
void has(const std::string&s,const std::string&needle){if(s.find(needle)==std::string::npos){std::cerr<<"Missing "<<needle<<" in "<<s;std::abort();}}
int main(){
 fresh();has(run("HELLO"),"\"protocol\":1");
 fresh();has(run("SCAN"),"\"uid\":\"11223344\"");assert(!cardSelected);
 fresh();reader.version=0;has(run("SCAN"),"READER_UNAVAILABLE");assert(reader.authCalls==0&&reader.writes.empty());
 fresh();reader.present=false;has(run("SCAN"),"NO_TAG");assert(nowMs>=5000&&nowMs<5100);
 for(const char*line:{"WRITE 11223344 0 FFFFFFFFFFFF 00112233445566778899AABBCCDDEEFF","WRITE 11223344 7 FFFFFFFFFFFF 00112233445566778899AABBCCDDEEFF","WRITE 11223344 4 FFFFFFFFFFFF 0011XX33445566778899AABBCCDDEEFF","WRITE 11223344 4 FFFFFFFFFFFF 0011","KEY 11223344 FFFFFFFFFFFF ABC","KEY 11223344 FFFFFFFFFFFF 1234567890AB EXTRA","WRITE 11223344 4 FFFFFFFFFFFF 00112233445566778899AABBCCDDEEFF EXTRA","HELLO EXTRA"}){fresh();has(run(line),"PARSE_ERROR");assert(reader.writes.empty()&&reader.authCalls==0);}
 fresh();has(run("WRITE 11223345 4 FFFFFFFFFFFF 00112233445566778899AABBCCDDEEFF"),"UID_MISMATCH");assert(reader.writes.empty()&&reader.authCalls==0&&!cardSelected);
 fresh();reader.uid.size=7;has(run("KEY 11223344 FFFFFFFFFFFF 1234567890AB"),"UNSUPPORTED_TAG");assert(reader.writes.empty()&&reader.authCalls==0);
 fresh();has(run("WRITE 11223344 4 000000000000 00112233445566778899AABBCCDDEEFF"),"AUTH_FAILED");assert(reader.writes.empty());
 fresh();has(run("WRITE 11223344 4 FFFFFFFFFFFF 00112233445566778899AABBCCDDEEFF"),"\"verified\":true");assert(reader.writes==std::vector<int>{4}&&reader.blocks[4][15]==0xFF&&!cardSelected);
 fresh();reader.failWrite=true;has(run("WRITE 11223344 4 FFFFFFFFFFFF 00112233445566778899AABBCCDDEEFF"),"WRITE_FAILED");assert(reader.writes.empty());
 fresh();reader.corruptReadback=true;has(run("WRITE 11223344 4 FFFFFFFFFFFF 00112233445566778899AABBCCDDEEFF"),"VERIFY_FAILED");
 fresh();reader.blocks[7][8]=0;has(run("KEY 11223344 FFFFFFFFFFFF 1234567890AB"),"ACCESS_BITS");assert(reader.writes.empty());
 fresh();has(run("KEY 11223344 FFFFFFFFFFFF 16785090548E"),"\"verified\":true");assert(reader.writes==std::vector<int>{7});assert(reader.authCalls==2);assert(reader.blocks[7][6]==0xFF&&reader.blocks[7][7]==7&&reader.blocks[7][8]==0x80&&reader.blocks[7][9]==0x45);assert((reader.activeKey==std::array<byte,6>{0x16,0x78,0x50,0x90,0x54,0x8E}));assert(std::memcmp(reader.blocks[7].data(),reader.blocks[7].data()+10,6)==0&&!cardSelected);
 fresh();has(run("READ 11223344 7 FFFFFFFFFFFF"),"\"data\":\"000000000000FF078045FFFFFFFFFFFF\"");
 fresh();Serial.feed("WRITE 11223344 4 FFFFFFFFFFFF 00112233445566778899AABBCCDDEEFF "+std::string(250,'A')+"\nHELLO\n");loop();has(Serial.out,"PARSE_ERROR");has(Serial.out,"\"cmd\":\"HELLO\"");assert(reader.writes.empty());
 fresh();Serial.feed(std::string("WRITE 11223344 4 FFFFFFFFFFFF ")+std::string(1,'\0')+"00112233445566778899AABBCCDDEEFF\n");loop();has(Serial.out,"PARSE_ERROR");assert(reader.writes.empty());
 fresh();has(run("BAD\"CMD"),"\"cmd\":\"INPUT\"");

 fresh();has(run("NTBAD\"CMD"),"\"cmd\":\"INPUT\"");
 auto ultra=[](){fresh();reader.uid.size=7;reader.ultra=true;for(int i=0;i<7;++i)reader.uid.uidByte[i]=i+1;};
 ultra();has(run("NTSCAN"),"NTAG213");assert(reader.writes.empty()&&!cardSelected);
 for(const char*page:{"0","1","2","3","40","41","42","43","44","45","255","-1","5x"}) {
   ultra();has(run(std::string("NTWRITE 01020304050607 ")+page+" 11223344"),"PARSE_ERROR");assert(reader.writes.empty());
 }
 fresh();has(run("NTWRITE 01020304050607 4 11223344"),"UNSUPPORTED_TAG");assert(reader.writes.empty());
 ultra();has(run("WRITE 01020304 4 FFFFFFFFFFFF 00112233445566778899AABBCCDDEEFF"),"UNSUPPORTED_TAG");assert(reader.writes.empty());
 ultra();has(run("NTWRITE 01020304050608 4 11223344"),"UID_MISMATCH");assert(reader.writes.empty());
 ultra();reader.tagVersion=0x11;has(run("NTWRITE 01020304050607 4 11223344"),"UNSUPPORTED_TAG");assert(reader.writes.empty());
 for(int field:{10,11,160,161,162,167}) {
   ultra();reader.pages[field/4][field%4]=1;has(run("NTWRITE 01020304050607 4 11223344"),"ACCESS_BITS");assert(reader.writes.empty());
 }
 ultra();auto pages=reader.pages;has(run("NTWRITE 01020304050607 4 11223344"),"verified");assert(reader.writes==std::vector<int>{4});
 for(int p=0;p<45;++p)if(p!=4)assert(reader.pages[p]==pages[p]);
 ultra();has(run("NTWRITE 01020304050607 39 AABBCCDD"),"verified");assert(reader.writes==std::vector<int>{39});
 ultra();reader.corruptReadback=true;has(run("NTWRITE 01020304050607 4 11223344"),"VERIFY_FAILED");
 ultra();has(run("NTREAD 01020304050607 40"),"data");assert(reader.writes.empty());
 std::cout<<"Firmware mock checks passed: framing, UID binding, allowed blocks, authentication, write readback, key/access preservation.\n";
}
