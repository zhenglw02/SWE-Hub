function testOperations(a: number, b: number, c: number): number | undefined {
  let result: number;

  // 目标: FlipOperator (>), ChangeModifier (-), SwapOperands
  if (a > b) {
    result = a - b;
  } else {
    result = b - a;
  }
  
  // 目标: FlipOperator (&&, ||), ChangeModifier (|)
  if (a && b) {
    result = a | b;
  }
  
  // 目标: FlipOperator (===)
  if (result === 0) {
    console.log("Result is zero");
  }

  // 目标: BreakChainsModifier
  let chainResult = a + b + c; 
  
  // 目标: ChangeConstantsModifier (十进制)
  result = chainResult + 5; 
  let count = result * 10;
  
  // 目标: ChangeConstantsModifier (十六进制)
  let flags = count & 0xFF; 

  if (count > 20) {
    return 0;
  }
  
  let items: number[] = [1, 2, 3];
  let binaryMask: number = 0b1010;

  return result;
}