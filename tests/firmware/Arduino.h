// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <string>
#include <sstream>
#include <deque>
#include <iomanip>
using byte=uint8_t;
#define F(s) s
constexpr int HEX=16;
inline unsigned long nowMs=0;
inline unsigned long millis(){return nowMs;}
inline void delay(unsigned long ms){nowMs+=ms;}
struct FakeSerial {
 std::string out;
 std::deque<unsigned char> in;
 void begin(int){}
 void print(const char*s){out+=s;}
 void print(char c){out+=c;}
 void print(unsigned char c){out+=std::to_string(c);}
 void print(unsigned char c,int base){std::ostringstream s; if(base==HEX)s<<std::uppercase<<std::hex<<static_cast<unsigned>(c);else s<<static_cast<unsigned>(c);out+=s.str();}
 template<class T>void print(T v){out+=std::to_string(v);}
 template<class T>void println(T v){print(v);out+='\n';}
 void println(){out+='\n';}
 int available(){return !in.empty();}
 int read(){int v=in.front();in.pop_front();return v;}
 void feed(const std::string&s){in.insert(in.end(),s.begin(),s.end());}
};
inline FakeSerial Serial;
