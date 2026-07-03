// Conformance fixture (BACK-422 Tier 1) — C#
using System;
using System.IO;
using System.Text;  // unused on purpose -- must still be flagged by imports://

namespace Sample
{
    public class OrderProcessor
    {
        public static int Validate(int order)
        {
            if (order == 0)
            {
                throw new ArgumentException("empty order");
            }
            return order;
        }

        public static int ProcessOrder(int order)
        {
            int result = Validate(order);
            try
            {
                File.AppendAllText("/tmp/orders.log", result.ToString());
            }
            catch (IOException)
            {
                return -1;
            }
            result = result * 2;
            return result;
        }

        public static int Run(int order)
        {
            return ProcessOrder(order);
        }
    }
}
