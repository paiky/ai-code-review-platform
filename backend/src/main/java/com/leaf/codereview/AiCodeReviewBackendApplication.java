package com.leaf.codereview;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@EnableAsync
@SpringBootApplication
public class AiCodeReviewBackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(AiCodeReviewBackendApplication.class, args);
    }
}
