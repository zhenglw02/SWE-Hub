// entity_extraction_test_case.ts

/**
 * 这是一个全面的 TypeScript 测试用例文件，
 * 用于验证 entity_query 是否能正确捕获所有类型的代码实体。
 */

// 1. 对应: (function_declaration ... )
//    - 这是一个标准的、顶层的函数声明。
export function standaloneFunction(param: string): string {
    return `Input was: ${param}`;
}


// 2. & 3. 对应: (class_declaration ... ) 和 (method_definition ... )
export class Vehicle {
    private speed: number = 0;

    // 对应: (method_definition ...), name 是特殊的 "constructor"
    constructor(startSpeed: number) {
        this.speed = startSpeed;
    }

    // 对应: (method_definition ...), name 是 "accelerate"
    public accelerate(amount: number): void {
        this.speed += amount;
    }
}


// 4. 对应: (lexical_declaration (variable_declarator value: (arrow_function)))
//    - 这是一个被赋值给 `const` 变量的箭头函数。
export const utilityFunction = (a: number, b: number): number => {
    return a * b;
};


// 5. 对应: (interface_declaration ... )
//    - 这是一个 TypeScript 特有的接口声明。
export interface Drawable {
    id: string;
    draw(context: any): void;
}


// 6. 对应: (type_alias_declaration ... )
//    - 这是一个 TypeScript 特有的类型别名声明。
export type Coordinate = {
    x: number;
    y: number;
};

// 一个不应该被捕获为实体的普通变量
const PI = 3.14;