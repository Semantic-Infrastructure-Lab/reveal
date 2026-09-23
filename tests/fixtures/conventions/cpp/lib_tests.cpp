#include <gtest/gtest.h>
#include "lib.h"

TEST(LibTest, Used) {
    Lib l;
    EXPECT_EQ(l.used(), 0);
}
