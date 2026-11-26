// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#pragma once
#include "Arduino.h"
#include <array>
#include <cassert>
#include <vector>
struct MFRC522 {
 enum StatusCode{STATUS_OK,STATUS_ERROR,STATUS_COLLISION};
 enum PICC_Type{PICC_TYPE_MIFARE_1K,PICC_TYPE_OTHER,PICC_TYPE_MIFARE_UL};
 enum{VersionReg=0x37,PICC_CMD_MF_AUTH_KEY_A=0x60};
 struct MIFARE_Key{byte keyByte[6];};
 struct Uid{byte size=4;byte uidByte[10]={0x11,0x22,0x33,0x44};byte sak=8;}uid;
 byte version=0x92;
 bool ultra=false;byte tagVersion=0x0F;
 std::array<std::array<byte,4>,45> pages{};
 bool present=true,supported=true,failWrite=false,corruptReadback=false;
 int authCalls=0,readCalls=0;
 std::array<byte,6> activeKey;
 std::array<std::array<byte,16>,8> blocks{};
 std::vector<int>writes;
 MFRC522(byte,byte){reset();}
 void reset(){ultra=false;tagVersion=0x0F;for(auto&p:pages)p.fill(0);pages[3]={0xE1,0x10,0x12,0};pages[41][3]=0xFF;version=0x92;present=true;supported=true;failWrite=false;corruptReadback=false;authCalls=0;readCalls=0;writes.clear();activeKey.fill(0xFF);uid.size=4;uid.uidByte[0]=0x11;uid.uidByte[1]=0x22;uid.uidByte[2]=0x33;uid.uidByte[3]=0x44;uid.sak=8;for(auto&b:blocks)b.fill(0);blocks[7].fill(0xFF);blocks[7][6]=0xFF;blocks[7][7]=0x07;blocks[7][8]=0x80;blocks[7][9]=0x45;}
 void PCD_Init(){}
 byte PCD_ReadRegister(int){return version;}
 void PCD_StopCrypto1(){}
 StatusCode PICC_HaltA(){return STATUS_OK;}
 StatusCode PICC_WakeupA(byte*,byte*){return present?STATUS_OK:STATUS_ERROR;}
 bool PICC_ReadCardSerial(){return present;}
 PICC_Type PICC_GetType(byte){return ultra?PICC_TYPE_MIFARE_UL:supported?PICC_TYPE_MIFARE_1K:PICC_TYPE_OTHER;}
 StatusCode PCD_Authenticate(int,byte,MIFARE_Key*key,Uid*){++authCalls;return std::memcmp(activeKey.data(),key->keyByte,6)==0?STATUS_OK:STATUS_ERROR;}
 StatusCode MIFARE_Read(byte block,byte*data,byte*len){++readCalls;if(ultra){assert(block<=40);for(int p=0;p<4;++p)std::memcpy(data+p*4,pages[block+p].data(),4);if(corruptReadback&&!writes.empty())data[0]^=1;*len=18;return STATUS_OK;}std::memcpy(data,blocks[block].data(),16);if(block==7)std::memset(data,0,6);if(corruptReadback&&!writes.empty())data[0]^=1;*len=18;return STATUS_OK;}
 StatusCode PCD_CalculateCRC(byte*,byte,byte*out){out[0]=out[1]=0;return STATUS_OK;}
 StatusCode PCD_TransceiveData(byte*,byte,byte*out,byte*len,byte*,byte,bool){assert(ultra);byte v[10]={0,4,4,2,1,0,tagVersion,3,0,0};std::memcpy(out,v,10);*len=10;return STATUS_OK;}
 StatusCode MIFARE_Ultralight_Write(byte page,byte*data,byte len){assert(ultra&&page>=4&&page<=39&&len==4);if(failWrite)return STATUS_ERROR;writes.push_back(page);std::memcpy(pages[page].data(),data,4);return STATUS_OK;}
 StatusCode MIFARE_Write(byte block,byte*data,byte len){if(failWrite||len!=16)return STATUS_ERROR;writes.push_back(block);std::memcpy(blocks[block].data(),data,16);if(block==7)std::memcpy(activeKey.data(),data,6);return STATUS_OK;}
};
