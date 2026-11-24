module.exports = {
    devServer: {
        proxy: {
            // 任务(2)：新接口 /api/v1/* 直接代理到 5000，不重写路径
            '/api/v1': {
                target: 'http://localhost:5000',
                changeOrigin: true,
            },
            // 旧接口保持原行为：/api/xxx -> /xxx
            '/api': {
                target: 'http://localhost:5000', // 要代理到的目标服务器
                changeOrigin: true,
                pathRewrite: {
                    '^/api': '', // 可选的路径重写规则
                },
            },
        },
    },
};