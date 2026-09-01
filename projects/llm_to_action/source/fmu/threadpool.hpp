#include <mutex>
#include <atomic>
#include <functional>
#include <queue>
#include <condition_variable>
#include <thread>
#include <vector>
#include <util2/C/marker5.h>


class ThreadPool 
{
public:
    using Task = std::function<void()>;

    ThreadPool() : m_stop{true} {} // Start dead

    ~ThreadPool() {
        markstr("destructor_begin");
        destroy();
        markstr("destructor_end");
    }


    void create(uint8_t num_threads) 
    {
        markstr("create_begin");
        std::unique_lock<std::mutex> lock(m_queueLock);
        if (!m_stop) {
            return; // Already running
        }
        m_stop = false;

        auto work = [this] {
            for(;;) 
            {
                std::function<void()> task;
                {
                    /* Out-of-scope will unlock queue mutex */
                    std::unique_lock<std::mutex> lock(this->m_queueLock);
                    this->m_cv.wait(lock, [this]{ 
                        return this->m_stop || !this->m_taskQ.empty(); 
                    });

                    if(this->m_stop && this->m_taskQ.empty()) {
                        return;
                    }
                    task = std::move(this->m_taskQ.front());
                    this->m_taskQ.pop();
                }
                
                markstr("task_start");
                task();
                markstr("task_end");
            }
        };

        for(uint8_t i = 0; i < num_threads; ++i) {
            m_workers.emplace_back(work);
        }
        markstr("create_end");
        return;
    }


    void destroy() {
        markstr("destroy_begin");
        {
            std::unique_lock<std::mutex> lock(m_queueLock);
            if (m_stop) {
                markstr("destroy_already_called_once"); 
                return; 
            }
            m_stop = true;
        }
        m_cv.notify_all();

        /* Join all currently pending & free threads */
        for(std::thread& worker : m_workers) { 
            if(worker.joinable()) {
                worker.join();
            }
        }
        m_workers.clear();
        markstr("destroy_end");
        return;
    }


    void enqueue(std::function<void()> task) {
        {
            std::unique_lock<std::mutex> lock(m_queueLock);
            if (m_stop) {
                return; // Drop tasks if dead
            }
            m_taskQ.emplace(std::move(task));
        }
        m_cv.notify_one();
        return;
    }


private:
    std::vector<std::thread> m_workers;
    std::queue<Task>         m_taskQ;
    std::mutex               m_queueLock;
    std::condition_variable  m_cv;
    std::atomic<bool>        m_stop;
};