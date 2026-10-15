## Bài 1.1

### Số liệu 
```sh
/block: 5.06 s -> {'message': 'This endpoint running on thread MainThread blocks for 3 seconds.'}
/block: 8.07 s -> {'message': 'This endpoint running on thread MainThread blocks for 3 seconds.'}
/block: 11.07 s -> {'message': 'This endpoint running on thread MainThread blocks for 3 seconds.'}
Tổng thời gian /block: 11.07 s

/nonblock: 5.06 s -> {'message': 'This endpoint running on thread MainThread does not block for 3 seconds.'}
/nonblock: 5.06 s -> {'message': 'This endpoint running on thread MainThread does not block for 3 seconds.'}
/nonblock: 5.06 s -> {'message': 'This endpoint running on thread MainThread does not block for 3 seconds.'}
Tổng thời gian /nonblock: 5.06 s

/thread: 5.04 s -> {'message': 'This endpoint running on thread AnyIO worker thread blocks for 3 seconds.'}
/thread: 5.04 s -> {'message': 'This endpoint running on thread AnyIO worker thread blocks for 3 seconds.'}
/thread: 5.04 s -> {'message': 'This endpoint running on thread AnyIO worker thread blocks for 3 seconds.'}
Tổng thời gian /thread: 5.04 s
```

1. 