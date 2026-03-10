async function processFileContent(filePath, threshold) {
    /**
     * A sample function containing various structures to test removal modifiers.
     */

    // 目标: RemoveAssignModifier
    let dataPoints = [];

    // 目标: RemoveWrapperModifier / UnwrapWrapperModifier
    try {
        // (with 语句在 JS 中不常用，我们用 try-catch 来代表包装器)
        const fileContent = fs.readFileSync(filePath, 'utf8');
        const lines = fileContent.split('\n');

        // 目标: RemoveLoopModifier
        for (const line of lines) {
            if (!line) continue; // Skip empty lines

            let value = parseInt(line.trim(), 10);

            // 目标: RemoveConditionalModifier
            if (value > threshold) {
                
                // 目标: RemoveAssignModifier (augmented)
                value += 10;
                dataPoints.push(value);
            }
        }
    } catch (error) {
        // 这个 catch 块会和 try 一起被移除或解包
        console.error(`Error: File processing failed for ${filePath}`, error);
        return null;
    }

    return dataPoints;
}