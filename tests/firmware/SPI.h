// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
#pragma once
#include "Arduino.h"
struct FakeSPI{void begin(){}}; inline FakeSPI SPI;
