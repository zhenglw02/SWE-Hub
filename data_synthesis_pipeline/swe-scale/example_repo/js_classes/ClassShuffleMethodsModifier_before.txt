class DataService extends BaseService {
    static serviceName = "DataService";

    constructor(source) {
        super(source); // 继承父类构造函数
        this.data = [];
    }

    fetchData() {
        // A complex method body with some comments
        // to ensure formatting is preserved during shuffling.
        console.log(`Fetching data from ${this.source}...`);
        return Promise.resolve([1, 2, 3]);
    }
}