/*
 * SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
 * License: https://polyformproject.org/licenses/noncommercial/1.0.0
 * CFS Mega Bridge, protocol 1
 * Arduino Mega 2560 + MFRC522 (SS=53, RST=5, SPI=50/51/52).
 * The PC produces the Creality payload and UID-derived authentication keys.
 * CFS commands only read sector 1 and write its data blocks or keys.
 * Experimental NTAG213 commands only write user pages 4 through 39.
 * Lock, configuration, UID and password pages are never written.
 * Block 0, all other sectors, and arbitrary access-bit writes are unavailable.
 * Library: MFRC522 by GithubCommunity (tested compilation with 1.4.12).
 * Serial: 115200 baud; one command per line; one JSON response per command.
 */

#include <SPI.h>
#include <MFRC522.h>
#include <string.h>

#if defined(__AVR_ATmega328P__)
constexpr byte SS_PIN = 10;
constexpr byte RST_PIN = 9;
constexpr size_t LINE_CAPACITY = 128;
#else
constexpr byte SS_PIN = 53;
constexpr byte RST_PIN = 5;
constexpr size_t LINE_CAPACITY = 200;
#endif
constexpr unsigned long CARD_TIMEOUT_MS = 5000;

MFRC522 reader(SS_PIN, RST_PIN);
char inputLine[LINE_CAPACITY];
size_t inputLength = 0;
bool discardLine = false;
bool cardSelected = false;

// Commands, codes and messages passed here are fixed ASCII literals.
template <typename Code, typename Message>
void errorResponse(const char *command, Code code, Message message) {
  Serial.print(F("{\"ok\":false,\"cmd\":\""));
  Serial.print(command);
  Serial.print(F("\",\"code\":\""));
  Serial.print(code);
  Serial.print(F("\",\"message\":\""));
  Serial.print(message);
  Serial.println(F("\"}"));
}

void printHex(const byte *data, byte length) {
  for (byte i = 0; i < length; ++i) {
    if (data[i] < 0x10) Serial.print('0');
    Serial.print(data[i], HEX);
  }
}

void successPrefix(const char *command) {
  Serial.print(F("{\"ok\":true,\"cmd\":\""));
  Serial.print(command);
  Serial.print(F("\",\"uid\":\""));
  printHex(reader.uid.uidByte, reader.uid.size);
  Serial.print('"');
}

void releaseCard() {
  if (cardSelected) reader.PICC_HaltA();
  reader.PCD_StopCrypto1();
  cardSelected = false;
}

// Ensures early returns after authentication also end the card session.
struct CardGuard {
  ~CardGuard() { releaseCard(); }
};

byte readerVersion() {
  return reader.PCD_ReadRegister(MFRC522::VersionReg);
}

bool checkReader(const char *command) {
  byte version = readerVersion();
  if (version == 0x00 || version == 0xFF) {
    errorResponse(command, F("READER_UNAVAILABLE"), F("Check reader power and wiring."));
    return false;
  }
  return true;
}

void versionResponse(const char *command) {
  Serial.print(F("{\"ok\":true,\"cmd\":\""));
  Serial.print(command);
  Serial.print(F("\",\"protocol\":1,\"firmware_version\":\"1.1.0\",\"reader_version\":"));
  Serial.print(readerVersion());
#if defined(__AVR_ATmega328P__)
  Serial.print(F(",\"board\":\"nano328p\""));
#else
  Serial.print(F(",\"board\":\"mega2560\""));
#endif
  Serial.print(F(",\"capabilities\":[\"cfs_sector1\",\"ntag213\"]"));
  Serial.println('}');
}

int hexNibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}

bool decodeHex(const char *text, byte *output, byte length) {
  if (strlen(text) != static_cast<size_t>(length) * 2) return false;
  for (byte i = 0; i < length; ++i) {
    int high = hexNibble(text[i * 2]);
    int low = hexNibble(text[i * 2 + 1]);
    if (high < 0 || low < 0) return false;
    output[i] = static_cast<byte>((high << 4) | low);
  }
  return true;
}

bool parseBlock(const char *text, byte &block, bool allowTrailer) {
  if (text[0] < '4' || text[0] > (allowTrailer ? '7' : '6') || text[1] != '\0') {
    return false;
  }
  block = static_cast<byte>(text[0] - '0');
  return true;
}

bool selectCard(const char *command, const byte *expectedUid, bool ntag = false) {
  releaseCard();
  if (!checkReader(command)) return false;

  unsigned long started = millis();
  do {
    byte atqa[2];
    byte atqaSize = sizeof(atqa);
    MFRC522::StatusCode status = reader.PICC_WakeupA(atqa, &atqaSize);
    if (status == MFRC522::STATUS_OK || status == MFRC522::STATUS_COLLISION) {
      if (!reader.PICC_ReadCardSerial()) {
        errorResponse(command, F("READ_FAILED"), F("Card selection failed; remove and retry."));
        return false;
      }
      cardSelected = true;

      if ((ntag && (reader.uid.size != 7 || reader.PICC_GetType(reader.uid.sak) != MFRC522::PICC_TYPE_MIFARE_UL)) ||
          (!ntag && (reader.uid.size != 4 || reader.PICC_GetType(reader.uid.sak) != MFRC522::PICC_TYPE_MIFARE_1K))) {
        errorResponse(command, F("UNSUPPORTED_TAG"), F("Use MIFARE Classic 1K with a four-byte UID."));
        return false;
      }
      if (expectedUid != nullptr && memcmp(reader.uid.uidByte, expectedUid, ntag ? 7 : 4) != 0) {
        errorResponse(command, F("UID_MISMATCH"), F("A different card is on the reader."));
        return false;
      }
      return true;
    }
    delay(25);
  } while (millis() - started < CARD_TIMEOUT_MS);

  errorResponse(command, F("NO_TAG"), F("No tag detected within five seconds."));
  return false;
}

bool authenticate(const char *command, byte block, const byte *keyBytes) {
  MFRC522::MIFARE_Key key;
  memcpy(key.keyByte, keyBytes, sizeof(key.keyByte));
  MFRC522::StatusCode status = reader.PCD_Authenticate(
      MFRC522::PICC_CMD_MF_AUTH_KEY_A, block, &key, &reader.uid);
  if (status != MFRC522::STATUS_OK) {
    errorResponse(command, F("AUTH_FAILED"), F("Sector authentication failed."));
    return false;
  }
  return true;
}

bool readBlock(const char *command, byte block, byte *output) {
  byte buffer[18];
  byte length = sizeof(buffer);
  if (reader.MIFARE_Read(block, buffer, &length) != MFRC522::STATUS_OK || length < 16) {
    errorResponse(command, F("READ_FAILED"), F("Reading the selected block failed."));
    return false;
  }
  memcpy(output, buffer, 16);
  return true;
}

// NTAG213 has a different tag type, UID length and command namespace.
// The type/version/range checks below run on every command, before writes.
bool ntagVersion(const char *command) {
  byte request[3] = {0x60, 0, 0};
  if (reader.PCD_CalculateCRC(request, 1, request + 1) != MFRC522::STATUS_OK) {
    errorResponse(command, F("READ_FAILED"), F("Cannot calculate GET_VERSION CRC."));
    return false;
  }
  byte version[10];
  byte length = sizeof(version);
  if (reader.PCD_TransceiveData(request, sizeof(request), version, &length, nullptr, 0, true) != MFRC522::STATUS_OK ||
      length != 10 || version[0] != 0 || version[1] != 4 || version[2] != 4 || version[6] != 0x0F) {
    errorResponse(command, F("UNSUPPORTED_TAG"), F("NTAG213 GET_VERSION required."));
    return false;
  }
  return true;
}

bool parsePage(const char *text, byte &page, bool writing) {
  size_t n = strlen(text);
  if (n == 0 || n > 2) return false;
  unsigned int value = 0;
  for (size_t i = 0; i < n; ++i) {
    if (text[i] < '0' || text[i] > '9') return false;
    value = value * 10 + text[i] - '0';
  }
  if (writing ? (value < 4 || value > 39) : value > 40) return false;
  page = static_cast<byte>(value);
  return true;
}

bool ntagUnlocked(const char *command) {
  byte system[16];
  byte config[16];
  if (!readBlock(command, 0, system) || !readBlock(command, 40, config)) return false;
  if (system[10] || system[11] || system[12] != 0xE1 || system[13] != 0x10 ||
      system[14] != 0x12 || system[15] != 0 || config[0] || config[1] || config[2] || config[7] != 0xFF) {
    errorResponse(command, F("ACCESS_BITS"), F("Locked/protected/nonstandard NTAG213; no writes allowed."));
    return false;
  }
  return true;
}

void ntagCommand(char **tokens, byte count) {
  const char *command = tokens[0];
  bool scan = strcmp(command, "NTSCAN") == 0;
  bool read = strcmp(command, "NTREAD") == 0;
  bool write = strcmp(command, "NTWRITE") == 0;
  if (!scan && !read && !write) {
    errorResponse("INPUT", F("PARSE_ERROR"), F("Unknown NTAG command."));
    return;
  }
  if (count != (scan ? 1 : read ? 3 : 4)) {
    errorResponse(command, F("PARSE_ERROR"), F("Unknown NTAG command or argument count."));
    return;
  }
  byte uid[7];
  byte page = 0;
  byte data[4];
  if (!scan && (!decodeHex(tokens[1], uid, 7) || !parsePage(tokens[2], page, write))) {
    errorResponse(command, F("PARSE_ERROR"), F("Expected 7-byte UID; reads 0-40, writes 4-39 only."));
    return;
  }
  if (write && !decodeHex(tokens[3], data, 4)) {
    errorResponse(command, F("PARSE_ERROR"), F("A page contains exactly four bytes."));
    return;
  }
  CardGuard guard;
  if (!selectCard(command, scan ? nullptr : uid, true) || !ntagVersion(command)) return;
  if (scan) {
    successPrefix(command);
    Serial.println(F(",\"type\":\"NTAG213\",\"uid_size\":7}"));
    return;
  }
  if (write) {
    if (!ntagUnlocked(command)) return;
    if (reader.MIFARE_Ultralight_Write(page, data, 4) != MFRC522::STATUS_OK) {
      errorResponse(command, F("WRITE_FAILED"), F("NTAG213 page write failed."));
      return;
    }
  }
  byte actual[16];
  // A page read returns four consecutive pages. For page 39 only compare the
  // first four bytes; following read-only config bytes are never written.
  if (!readBlock(command, page, actual)) return;
  if (write && memcmp(data, actual, 4) != 0) {
    errorResponse(command, F("VERIFY_FAILED"), F("NTAG213 page readback failed."));
    return;
  }
  successPrefix(command);
  Serial.print(F(",\"page\":"));
  Serial.print(page);
  if (write) {
    Serial.println(F(",\"verified\":true}"));
  } else {
    Serial.print(F(",\"data\":\""));
    printHex(actual, sizeof(actual));
    Serial.println(F("\"}"));
  }
}

void handleCommand(char *line) {
  char *tokens[6];
  byte count = 0;
  char *context = nullptr;
  char *token = strtok_r(line, " \t", &context);
  while (token != nullptr) {
    if (count >= 6) {
      errorResponse("INPUT", F("PARSE_ERROR"), F("Too many command arguments."));
      return;
    }
    tokens[count++] = token;
    token = strtok_r(nullptr, " \t", &context);
  }
  if (count == 0) return;

  if (strcmp(tokens[0], "HELLO") == 0) {
    if (count != 1) {
      errorResponse("HELLO", F("PARSE_ERROR"), F("HELLO takes no arguments."));
      return;
    }
    if (checkReader("HELLO")) versionResponse("HELLO");
    return;
  }

  if (strcmp(tokens[0], "SCAN") == 0) {
    if (count != 1) {
      errorResponse("SCAN", F("PARSE_ERROR"), F("SCAN takes no arguments."));
      return;
    }
    CardGuard guard;
    if (!selectCard("SCAN", nullptr)) return;
    successPrefix("SCAN");
    Serial.print(F(",\"type\":\"MIFARE_1K\",\"sak\":"));
    Serial.print(reader.uid.sak);
    Serial.print(F(",\"uid_size\":"));
    Serial.print(reader.uid.size);
    Serial.println('}');
    return;
  }

  if (strncmp(tokens[0], "NT", 2) == 0) {
    ntagCommand(tokens, count);
    return;
  }

  bool isRead = strcmp(tokens[0], "READ") == 0;
  bool isWrite = strcmp(tokens[0], "WRITE") == 0;
  bool isKey = strcmp(tokens[0], "KEY") == 0;
  const char *command = isRead ? "READ" : isWrite ? "WRITE" : isKey ? "KEY" : "INPUT";
  if (!isRead && !isWrite && !isKey) {
    errorResponse(command, F("PARSE_ERROR"), F("Unknown command."));
    return;
  }
  if (count != (isWrite ? 5 : 4)) {
    errorResponse(command, F("PARSE_ERROR"), F("Incorrect command argument count."));
    return;
  }

  byte uid[4];
  byte key[6];
  byte newKey[6];
  byte data[16];
  byte block = 0;
  if (!decodeHex(tokens[1], uid, 4)) {
    errorResponse(command, F("PARSE_ERROR"), F("UID must contain eight hexadecimal characters."));
    return;
  }
  if (isKey) {
    if (!decodeHex(tokens[2], key, 6) || !decodeHex(tokens[3], newKey, 6)) {
      errorResponse(command, F("PARSE_ERROR"), F("Keys must contain twelve hexadecimal characters."));
      return;
    }
  } else {
    if (!parseBlock(tokens[2], block, isRead) || !decodeHex(tokens[3], key, 6)) {
      errorResponse(command, F("PARSE_ERROR"), F("Use a sector-one block and twelve hexadecimal key characters."));
      return;
    }
    if (isWrite && !decodeHex(tokens[4], data, 16)) {
      errorResponse(command, F("PARSE_ERROR"), F("Data must contain thirty-two hexadecimal characters."));
      return;
    }
  }

  CardGuard guard;
  if (!selectCard(command, uid)) return;
  if (!authenticate(command, isKey ? 7 : block, key)) return;

  if (isRead) {
    if (!readBlock(command, block, data)) return;
    successPrefix(command);
    Serial.print(F(",\"block\":"));
    Serial.print(block);
    Serial.print(F(",\"data\":\""));
    printHex(data, sizeof(data));
    Serial.println(F("\"}"));
    return;
  }

  if (isWrite) {
    if (reader.MIFARE_Write(block, data, sizeof(data)) != MFRC522::STATUS_OK) {
      errorResponse(command, F("WRITE_FAILED"), F("Writing the selected block failed."));
      return;
    }
    byte actual[16];
    if (!readBlock(command, block, actual)) return;
    if (memcmp(data, actual, sizeof(data)) != 0) {
      errorResponse(command, F("VERIFY_FAILED"), F("Written data did not match readback."));
      return;
    }
    successPrefix(command);
    Serial.print(F(",\"block\":"));
    Serial.print(block);
    Serial.println(F(",\"verified\":true}"));
    return;
  }

  // KEY is the only way to modify a trailer. Keep the access bits and GP byte.
  byte trailer[16];
  if (!readBlock(command, 7, trailer)) return;
  if (trailer[6] != 0xFF || trailer[7] != 0x07 || trailer[8] != 0x80) {
    errorResponse(command, F("ACCESS_BITS"), F("Only transport access bits FF0780 are supported."));
    return;
  }
  byte accessAndGp[4];
  memcpy(accessAndGp, trailer + 6, sizeof(accessAndGp));
  memcpy(trailer, newKey, 6);
  memcpy(trailer + 10, newKey, 6);
  if (reader.MIFARE_Write(7, trailer, sizeof(trailer)) != MFRC522::STATUS_OK) {
    errorResponse(command, F("WRITE_FAILED"), F("Writing the sector keys failed."));
    return;
  }

  // New keys only take effect after ending the previous authenticated session.
  releaseCard();
  if (!selectCard(command, uid) || !authenticate(command, 7, newKey)) return;
  byte actualTrailer[16];
  if (!readBlock(command, 7, actualTrailer)) return;
  if (memcmp(actualTrailer + 6, accessAndGp, sizeof(accessAndGp)) != 0 ||
      memcmp(actualTrailer + 10, newKey, 6) != 0) {
    errorResponse(command, F("VERIFY_FAILED"), F("Sector key verification failed."));
    return;
  }
  successPrefix(command);
  Serial.println(F(",\"verified\":true}"));
}

void setup() {
  Serial.begin(115200);
  SPI.begin();
  reader.PCD_Init();
  delay(50);
  versionResponse("BOOT");
}

void loop() {
  while (Serial.available() > 0) {
    int incoming = Serial.read();
    if (incoming == '\r') continue;
    if (incoming == '\n') {
      if (discardLine) {
        errorResponse("INPUT", F("PARSE_ERROR"), F("Command line too long or contains non-ASCII data."));
      } else {
        inputLine[inputLength] = '\0';
        handleCommand(inputLine);
      }
      inputLength = 0;
      discardLine = false;
      continue;
    }
    if (discardLine) continue;
    if ((incoming < 0x20 && incoming != '\t') || incoming > 0x7E ||
        inputLength >= LINE_CAPACITY - 1) {
      discardLine = true;
      continue;
    }
    inputLine[inputLength++] = static_cast<char>(incoming);
  }
}
