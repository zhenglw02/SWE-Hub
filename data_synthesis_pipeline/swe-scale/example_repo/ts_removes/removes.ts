async function testRemovals(filePath: string, threshold: number): Promise<number[] | null> {
  
  // ----------------------------------------------------
  // 目标: RemoveAssignModifier (lexical_declaration)
  let dataPoints: number[] = [];
  // ----------------------------------------------------

  // ----------------------------------------------------
  // 目标: RemoveWrapperModifier / UnwrapWrapperModifier
  try {
    const fileContent = fs.readFileSync(filePath, 'utf8');
    const lines = fileContent.split('\n');

    // ----------------------------------------------------
    // 目标: RemoveLoopModifier
    for (const line of lines) {
      if (!line) continue;

      // ----------------------------------------------------
      // 目标: RemoveAssignModifier (lexical_declaration)
      let value = parseInt(line.trim(), 10);
      // ----------------------------------------------------

      // ----------------------------------------------------
      // 目标: RemoveConditionalModifier
      if (value > threshold) {
        // ----------------------------------------------------
        // 目标: RemoveAssignModifier (augmented_assignment)
        value += 10;
        // ----------------------------------------------------
        dataPoints.push(value);
      }
      // ----------------------------------------------------
    }
    // ----------------------------------------------------

  } catch (error) {
    console.error(`Error: File processing failed for ${filePath}`, error);
    return null;
  }
  // ----------------------------------------------------

  return dataPoints;
}